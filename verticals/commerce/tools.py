"""The commerce agent's tools: real reads, server-joined UI, no write path at all."""

from __future__ import annotations

import asyncio

from ops_common.fencing import fence
from ops_common.skills import SkillRegistry
from ops_common.tools import ToolOutcome, ToolSpec

from .backend import CommerceBackend


def _run(fn, *args):
    return asyncio.to_thread(fn, *args)


def _product_row(row: dict) -> dict:
    return {
        "id": int(row["id"]), "name": row["name"], "category": row["category"],
        "price": float(row["price"]), "stock": int(row["stock"]), "sales_30d": int(row["sales_30d"]),
    }


def build_tools(backend: CommerceBackend, skills: SkillRegistry) -> list[ToolSpec]:
    async def load_skill(inp: dict, session) -> ToolOutcome:
        return ToolOutcome(content=skills.load(str(inp.get("name", ""))))

    async def search_products(inp: dict, session) -> ToolOutcome:
        keyword = str(inp.get("keyword", "")).strip()
        if not keyword:
            return ToolOutcome(status="error", content="缺少关键词。")
        category = (str(inp.get("category")) or "").strip() or None
        data = await _run(backend.search_goods, keyword, category)
        for row in data["rows"]:
            session.remember("product_ids", str(row["id"]))
        lines = [f"找到 {len(data['rows'])} 件（搜索耗时 {data['elapsed_ms']} ms，本店数据库实测）：" if data["rows"] else "没有找到匹配商品。"]
        lines += [
            f"- [{r['id']}] {r['name']} ｜ {r['category']} ｜ ¥{r['price']} ｜ 库存 {r['stock']} ｜ 近30天售出 {r['sales_30d']}"
            for r in data["rows"][:12]
        ]
        return ToolOutcome(
            content="\n".join(lines),
            ui={"component": "products", "payload": {"items": [_product_row(r) for r in data["rows"]], "elapsed_ms": data["elapsed_ms"]}},
        )

    async def get_product(inp: dict, session) -> ToolOutcome:
        try:
            pid = int(inp.get("product_id", 0))
        except (TypeError, ValueError):
            return ToolOutcome(status="error", content="product_id 需要是数字。")
        if not session.seen("product_ids", str(pid)):
            return ToolOutcome(
                status="blocked",
                content=f"已拦截（来源门控）：商品 {pid} 不是本次会话搜索结果里的商品。请先 search_products。",
            )
        row = await _run(backend.get_product, pid)
        if row is None:
            return ToolOutcome(status="error", content=f"商品 {pid} 不存在（可能刚下架）。")
        return ToolOutcome(content=fence(f"商品 {pid}", str(dict(row))))

    async def get_my_orders(inp: dict, session) -> ToolOutcome:
        try:
            user_id = int(inp.get("user_id", 42))
        except (TypeError, ValueError):
            return ToolOutcome(status="error", content="user_id 需要是数字。演示账号：42。")
        data = await _run(backend.get_user_orders, user_id)
        lines = [f"查到 {len(data['rows'])} 笔订单（查询耗时 {data['elapsed_ms']} ms）："]
        lines += [
            f"- 订单 {r['id']}：¥{r['total']} ｜ {r['status']} ｜ {r['channel']} ｜ {r['created_at']}"
            for r in data["rows"]
        ]
        return ToolOutcome(
            content="\n".join(lines),
            ui={
                "component": "orders",
                "payload": {
                    "items": [
                        {
                            "id": int(r["id"]), "total": float(r["total"]), "status": r["status"],
                            "channel": r["channel"], "created_at": str(r["created_at"]),
                            "elapsed_ms": data["elapsed_ms"],
                        }
                        for r in data["rows"]
                    ],
                    "elapsed_ms": data["elapsed_ms"],
                },
            },
        )

    async def get_business_snapshot(inp: dict, session) -> ToolOutcome:
        snap = await _run(backend.snapshot)
        content = (
            f"今日订单 {snap['orders_today']:,} 笔，销售额 ¥{snap['revenue_today']:,.2f}；"
            f"搜索 P99 {snap['search_p99_ms']} ms（均值 {snap['search_avg_ms']} ms）；"
            f"转化率 {snap['conversion_rate']}%（演示模拟：按延迟-转化关系推算）。"
            + ("数据库状态：健康。" if snap["db_healthy"] else "数据库状态：异常，搜索延迟显著偏高，建议到「数据库诊疗」台排查。")
        )
        return ToolOutcome(
            content=content,
            ui={"component": "metrics", "payload": snap},
        )

    return [
        ToolSpec(
            name="load_skill",
            description="加载流程手册（导购或运营分析前先加载）。",
            input_schema=skills.tool_input_schema(),
            handler=load_skill,
        ),
        ToolSpec(
            name="search_products",
            description="按关键词搜本店在售商品（可按类目过滤）。结果由门店数据库实测返回。",
            input_schema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string"},
                    "category": {"type": "string", "description": "可选类目，如：户外露营"},
                },
                "required": ["keyword"],
            },
            handler=search_products,
        ),
        ToolSpec(
            name="get_product",
            description="查看某个商品的详情。只接受本次会话搜索结果中出现过的商品 ID。",
            input_schema={
                "type": "object",
                "properties": {"product_id": {"type": "integer"}},
                "required": ["product_id"],
            },
            handler=get_product,
        ),
        ToolSpec(
            name="get_my_orders",
            description="查某个顾客的最近订单。演示账号 user_id=42。",
            input_schema={
                "type": "object",
                "properties": {"user_id": {"type": "integer"}},
                "required": ["user_id"],
            },
            handler=get_my_orders,
        ),
        ToolSpec(
            name="get_business_snapshot",
            description="今日经营快照：订单、销售额、搜索 P99 延迟（数据库实测）、转化率。",
            input_schema={"type": "object", "properties": {}},
            handler=get_business_snapshot,
        ),
    ]
