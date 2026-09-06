"""Run: .venv/bin/uvicorn server.app:app --port 8800  (from the repo root)."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from ops_common.types import Session                                    # noqa: E402
from verticals.commerce.agent import build as build_commerce            # noqa: E402
from verticals.mysql.agent import build as build_mysql                  # noqa: E402

DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

mysql_agent, mysql_store, mysql_backend, _guardrails = build_mysql(DATA_DIR)
commerce_agent, commerce_backend = build_commerce()

AGENTS = {"mysql": mysql_agent, "commerce": commerce_agent}
sessions: dict[str, Session] = {}

app = FastAPI(title="OpsAgents Demo", version="0.1.0")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)


def _session(agent_name: str, session_id: str | None) -> Session:
    if agent_name not in AGENTS:
        raise HTTPException(404, f"未知代理 {agent_name}")
    if session_id and session_id in sessions:
        return sessions[session_id]
    session = Session(session_id=session_id or uuid.uuid4().hex[:24], agent_name=agent_name)
    sessions[session.session_id] = session
    return session


@app.get("/api/health")
async def health():
    return {
        "ok": True,
        "model": mysql_agent.config.model,
        "mysql_version": await asyncio.to_thread(mysql_backend.server_version),
        "database": "ops_demo",
        "agents": sorted(AGENTS),
        "pending_changes": len(mysql_store.pending()),
    }


@app.post("/api/{agent_name}/session")
async def start_session(agent_name: str):
    session = _session(agent_name, None)
    return {"session_id": session.session_id}


@app.post("/api/{agent_name}/chat")
async def chat(agent_name: str, request: dict, x_session_id: str | None = Header(default=None)):
    session = _session(agent_name, x_session_id)
    message = str(request.get("message", "")).strip()
    if not message:
        raise HTTPException(400, "message 不能为空")

    async def event_stream():
        try:
            async for event in AGENTS[agent_name].stream_turn(session, message):
                yield event.sse()
        except Exception as error:  # the client gets a safe event; the log gets the rest
            import logging

            logging.getLogger(__name__).exception("chat turn failed")
            yield AgentEvent.error(f"服务端错误：{error.__class__.__name__}").sse()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/{agent_name}/overview")
async def overview(agent_name: str):
    if agent_name == "mysql":
        tables = await asyncio.to_thread(
            lambda: [mysql_backend.get_table_info(t) for t in mysql_backend.DEMO_TABLES]
        )
        slow = await asyncio.to_thread(mysql_backend.get_slow_queries, 5)
        return {
            "version": await asyncio.to_thread(mysql_backend.server_version),
            "database": "ops_demo",
            "slow_queries": slow,
            "tables": tables,
            "pending": [c.to_dict() for c in mysql_store.pending()],
            "recent_changes": [c.to_dict() for c in mysql_store.all()[:6]],
        }
    if agent_name == "commerce":
        snapshot = await asyncio.to_thread(commerce_backend.snapshot)
        recent = await asyncio.to_thread(commerce_backend.recent_orders, 8)
        return {
            "snapshot": snapshot,
            "recent_orders": [
                {
                    "id": int(r["id"]), "user_id": int(r["user_id"]), "total": float(r["total"]),
                    "status": r["status"], "channel": r["channel"], "created_at": str(r["created_at"]),
                }
                for r in recent
            ],
            "recent_changes": [c.to_dict() for c in mysql_store.all()[:6]],
        }
    raise HTTPException(404, f"未知代理 {agent_name}")


@app.get("/api/commerce/search")
async def storefront_search(keyword: str, category: str | None = None):
    """The storefront's own search box: real database, timed, logged — it feeds the story."""
    data = await asyncio.to_thread(commerce_backend.search_goods, keyword, category or None)
    return {"items": data["rows"], "elapsed_ms": data["elapsed_ms"]}


@app.get("/api/commerce/orders")
async def storefront_orders(user_id: int = 42):
    """The 'my orders' panel: the deliberately un-indexed query, timed for real."""
    data = await asyncio.to_thread(commerce_backend.get_user_orders, user_id)
    return {
        "items": [
            {"id": int(r["id"]), "total": float(r["total"]), "status": r["status"],
             "channel": r["channel"], "created_at": str(r["created_at"])}
            for r in data["rows"]
        ],
        "elapsed_ms": data["elapsed_ms"],
    }


@app.get("/api/changes")
async def all_changes():
    return {"changes": [c.to_dict() for c in mysql_store.all()]}


@app.post("/api/changes/{change_id}/apply")
async def apply_change(change_id: str, request: dict):
    approved_by = str(request.get("approved_by") or "DBA").strip() or "DBA"
    change = mysql_store.apply(change_id, approved_by)   # the approval mark: this route, a person
    sample_sql = change.impact.get("sample_sql")
    if sample_sql:
        after = await asyncio.to_thread(mysql_backend.measure, sample_sql)
        change.impact["after_ms"] = after["elapsed_ms"]
        mysql_store.update(change)
    return {"change": change.to_dict()}


@app.post("/api/changes/{change_id}/discard")
async def discard_change(change_id: str, request: dict):
    change = mysql_store.discard(change_id, str(request.get("by") or "DBA"))
    return {"change": change.to_dict()}


# The built console, when present, is served by the same process.
DIST = ROOT / "web" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
