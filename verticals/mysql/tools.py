"""The MySQL agent's tool surface. The governance ladder lives in these handlers."""

from __future__ import annotations

import asyncio
import hashlib

from ops_common.fencing import fence
from ops_common.skills import SkillRegistry
from ops_common.tools import ToolOutcome, ToolSpec
from ops_common.types import DiffItem, StagedChange

from . import gates
from .backend import MysqlBackend


def _run(fn, *args):
    return asyncio.to_thread(fn, *args)


def build_tools(backend: MysqlBackend, store, skills: SkillRegistry) -> list[ToolSpec]:
    async def load_skill(inp: dict, session) -> ToolOutcome:
        return ToolOutcome(content=skills.load(str(inp.get("name", ""))))

    async def get_slow_queries(inp: dict, session) -> ToolOutcome:
        limit = max(1, min(int(inp.get("limit", 5) or 5), 10))
        rows = await _run(backend.get_slow_queries, limit)
        lines = []
        for i, row in enumerate(rows, 1):
            key = hashlib.md5(gates.normalize(row["sample_text"]).lower().encode()).hexdigest()
            session.remember("sql", key)
            lines.append(
                f"{i}. 累计 {row['total_sec']}s × {row['count_star']} 次，平均 {row['avg_ms']}ms，"
                f"平均扫描 {int(row['rows_examined']):,} 行\n   样例：{row['sample_text']}"
            )
        content = "数据库自报的最慢 SELECT（performance_schema，按累计耗时排序）：\n" + "\n".join(lines) \
            if rows else "performance_schema 里没有本库的 SELECT 记录。"
        return ToolOutcome(content=content, ui={"component": "slow_queries", "payload": {"items": rows}})

    async def get_table_info(inp: dict, session) -> ToolOutcome:
        table = str(inp.get("table", "")).lower().strip()
        if table not in gates.ALLOWED_TABLES:
            return ToolOutcome(status="blocked", content=f"已拦截（来源门控）：{table or '（空）'} 不是演示库的表，白名单：{', '.join(gates.ALLOWED_TABLES)}。")
        info = await _run(backend.get_table_info, table)
        session.remember("tables", table)
        index_line = "；".join(f"{name}({','.join(cols)})" for name, cols in info["indexes"].items()) or "除主键外无二级索引"
        cols = "，".join(f"{c} {t}" for c, t in list(info["columns"].items())[:24])
        content = fence(
            f"表结构 {table}",
            f"行数 {info['rows']:,}，大小 {info['size_mb']} MB，引擎 {info['engine']}\n"
            f"索引：{index_line}\n列：{cols}",
        )
        return ToolOutcome(content=content)

    async def explain_query(inp: dict, session) -> ToolOutcome:
        ok, detail = gates.check_read_sql(str(inp.get("sql", "")))
        if not ok:
            return ToolOutcome(status="blocked", content=f"已拦截（SQL 读门控）：{detail}")
        sql = detail
        tree = await _run(backend.explain, sql)
        for table in gates.tables_in(sql):
            session.remember("tables", table)
        return ToolOutcome(
            content=fence("执行计划（EXPLAIN FORMAT=TREE）", tree),
            ui={"component": "plan_tree", "payload": {"sql": sql, "tree": tree}},
        )

    async def measure_query(inp: dict, session) -> ToolOutcome:
        ok, detail = gates.check_read_sql(str(inp.get("sql", "")))
        if not ok:
            return ToolOutcome(status="blocked", content=f"已拦截（SQL 读门控）：{detail}")
        sql = detail
        key = hashlib.md5(sql.lower().encode()).hexdigest()
        if not session.seen("sql", key):
            return ToolOutcome(
                status="blocked",
                content="已拦截（来源门控）：这条 SQL 不是本会话诊断工具给出的。请先 get_slow_queries 查看数据库自报的慢查询，或先 explain_query 一条已知的 SQL。",
            )
        result = await _run(backend.measure, sql)
        for table in gates.tables_in(sql):
            session.remember("tables", table)
        session.state.setdefault("measured", {})[sql] = result["elapsed_ms"]
        content = f"实测耗时 {result['elapsed_ms']} ms，返回 {len(result['rows'])} 行（行上限 50，超时上限 2s）。"
        return ToolOutcome(
            content=content,
            ui={"component": "measure", "payload": {"sql": sql, "elapsed_ms": result["elapsed_ms"], "rows": result["rows"]}},
        )

    async def stage_index_change(inp: dict, session) -> ToolOutcome:
        table = str(inp.get("table", "")).lower().strip()
        columns = [str(c).strip().lower() for c in (inp.get("columns") or []) if str(c).strip()]
        rationale = str(inp.get("rationale", "")).strip()
        if table not in gates.ALLOWED_TABLES:
            return ToolOutcome(status="blocked", content=f"已拦截（来源门控）：{table or '（空）'} 不在演示库白名单内。")
        if not session.seen("tables", table):
            return ToolOutcome(
                status="blocked",
                content=f"已拦截（来源门控）：本会话尚未诊断过 {table}。请先 get_table_info / explain_query / measure_query 再提变更。",
            )
        if not columns:
            return ToolOutcome(status="error", content="缺少索引列。")

        index_name = f"idx_{table}_{'_'.join(columns)}"
        change = StagedChange(
            kind="index",
            summary=f"为 {table} 增加索引 {index_name}({', '.join(columns)})",
            sql=f"ALTER TABLE `{table}` ADD INDEX {index_name} ({', '.join('`' + c + '`' for c in columns)})",
            items=[DiffItem(target=table, field="index", before="（无索引）", after=f"{index_name}({', '.join(columns)})")],
            impact={"table": table, "columns": columns, "rationale": rationale},
        )
        for sample_sql, ms in dict(session.state.get("measured", {})).items():
            if table in gates.tables_in(sample_sql):
                change.impact["sample_sql"] = sample_sql
                change.impact["before_ms"] = ms
                break
        try:
            stored = await _run(store.stage, change, gates.IndexGuardrails(backend))
        except ValueError as error:
            return ToolOutcome(status="blocked", content=f"已拦截（护栏）：{error}")
        return ToolOutcome(
            content=f"已暂存变更 {stored.change_id}。它只是建议——在你（DBA）于审批面点「批准」之前，数据库不会发生任何变化。我无法自己应用它。",
            change=stored.to_dict(),
        )

    async def get_pending_changes(inp: dict, session) -> ToolOutcome:
        pending = store.pending()
        content = "\n".join(f"- {c.change_id}：{c.summary}" for c in pending) or "当前没有待审批的变更。"
        return ToolOutcome(content="待审批变更：\n" + content if pending else content)

    return [
        ToolSpec(
            name="load_skill",
            description="加载一条流程手册（处理对应类别的请求前先加载）。",
            input_schema=skills.tool_input_schema(),
            handler=load_skill,
        ),
        ToolSpec(
            name="get_slow_queries",
            description="查看数据库自报的最慢 SELECT（performance_schema 汇总）。诊断一律从这里开始。",
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "description": "条数，1-10，默认 5"}},
            },
            handler=get_slow_queries,
        ),
        ToolSpec(
            name="get_table_info",
            description="查看演示库某张表的行数、大小、列和现有索引。评估索引前必看。",
            input_schema={
                "type": "object",
                "properties": {"table": {"type": "string", "enum": sorted(gates.ALLOWED_TABLES)}},
                "required": ["table"],
            },
            handler=get_table_info,
        ),
        ToolSpec(
            name="explain_query",
            description="对一条只读 SELECT 跑 EXPLAIN FORMAT=TREE，返回执行计划树。只允许单条 SELECT。",
            input_schema={
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "要解释的 SELECT 语句"}},
                "required": ["sql"],
            },
            handler=explain_query,
        ),
        ToolSpec(
            name="measure_query",
            description="实测执行一条 SQL 的耗时（2s 超时上限，最多返回 50 行）。只接受本会话诊断工具给出过的 SQL。",
            input_schema={
                "type": "object",
                "properties": {"sql": {"type": "string"}},
                "required": ["sql"],
            },
            handler=measure_query,
        ),
        ToolSpec(
            name="stage_index_change",
            description="把「增加索引」作为暂存变更提交，等待 DBA 审批。这是唯一的写路径，且它不执行任何东西。",
            input_schema={
                "type": "object",
                "properties": {
                    "table": {"type": "string", "enum": sorted(gates.ALLOWED_TABLES)},
                    "columns": {"type": "array", "items": {"type": "string"}, "description": "索引列，按顺序"},
                    "rationale": {"type": "string", "description": "一句话理由"},
                },
                "required": ["table", "columns", "rationale"],
            },
            handler=stage_index_change,
        ),
        ToolSpec(
            name="get_pending_changes",
            description="查看当前待审批的变更。",
            input_schema={"type": "object", "properties": {}},
            handler=get_pending_changes,
        ),
    ]
