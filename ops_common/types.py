"""Events and staged changes. One module so both verticals and the web client agree."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


@dataclass
class AgentEvent:
    """One streamed event; the SSE wire format and the shape the web client renders."""

    type: str
    data: dict = field(default_factory=dict)

    def sse(self) -> str:
        return f"data: {json.dumps({'type': self.type, **self.data}, ensure_ascii=False)}\n\n"

    @staticmethod
    def text(t: str) -> "AgentEvent":
        return AgentEvent("text_delta", {"text": t})

    @staticmethod
    def tool_call(tool: str, label: str) -> "AgentEvent":
        return AgentEvent("tool_call", {"tool": tool, "label": label})

    @staticmethod
    def tool_result(tool: str, status: str, summary: str) -> "AgentEvent":
        return AgentEvent("tool_result", {"tool": tool, "status": status, "summary": summary})

    @staticmethod
    def ui(component: str, payload: dict) -> "AgentEvent":
        return AgentEvent("ui", {"component": component, "payload": payload})

    @staticmethod
    def change_update(change: dict) -> "AgentEvent":
        return AgentEvent("change_update", {"change": change})

    @staticmethod
    def error(message: str) -> "AgentEvent":
        return AgentEvent("error", {"message": message})


@dataclass
class DiffItem:
    target: str
    field: str
    before: object
    after: object


@dataclass
class StagedChange:
    """A proposed write. Nothing applies until the host marks it approved."""

    kind: str                    # "index" | future write kinds
    summary: str
    sql: str = ""
    items: list[DiffItem] = field(default_factory=list)
    impact: dict = field(default_factory=dict)   # e.g. {"sample_sql": ..., "before_ms": 812.3}
    change_id: str = field(default_factory=lambda: f"chg-{uuid.uuid4().hex[:8]}")
    status: str = "staged"       # staged | applied | discarded
    created_by: str = "agent"
    created_by_kind: str = "agent"
    created_at: str = field(default_factory=now_iso)
    applied_at: str | None = None
    applied_by: str | None = None
    discarded_at: str | None = None
    discarded_by: str | None = None

    def to_dict(self) -> dict:
        return {
            "change_id": self.change_id, "kind": self.kind, "status": self.status,
            "summary": self.summary, "sql": self.sql,
            "items": [item.__dict__ for item in self.items],
            "impact": self.impact,
            "created_by": self.created_by, "created_by_kind": self.created_by_kind,
            "created_at": self.created_at,
            "applied_at": self.applied_at, "applied_by": self.applied_by,
            "discarded_at": self.discarded_at, "discarded_by": self.discarded_by,
        }


@dataclass
class Session:
    """One conversation: transcript, provenance state, and its lock-free single-turn use."""

    session_id: str
    agent_name: str
    messages: list[dict] = field(default_factory=list)
    # provenance: ids this session legitimately saw, e.g. {"table": set(), "sql": set()}
    state: dict = field(default_factory=dict)

    def remember(self, kind: str, value: str) -> None:
        self.state.setdefault(kind, set()).add(value)

    def seen(self, kind: str, value: str) -> bool:
        return value in self.state.get(kind, set())

    def context(self) -> dict:
        return {kind: sorted(values) for kind, values in self.state.items()}
