"""SQL gates: reads are checked statement-by-statement; writes only ever stage.

Ladder (loose to strict):
  explain_query   any gated read-only SELECT
  measure_query   gated SELECT + provenance: the text must have come from a diagnosis tool
  stage_index     table must have been diagnosed this session; guardrails re-run at apply
"""

from __future__ import annotations

import re

DB_NAME = None  # filled from env by backend

ALLOWED_TABLES = {"goods", "orders", "search_log"}
READ_PREFIX = ("select",)
FORBIDDEN = re.compile(
    r"(?i)\b(insert|update|delete|drop|alter|create|truncate|rename|grant|revoke|replace|call|"
    r"load_file|outfile|dumpfile|set|use|lock|unlock|shutdown|kill|prepare|execute)\b"
)
_COMMENT = re.compile(r"(--[^\n]*|#[^\n]*|/\*.*?\*/)", re.S)
_TABLE_REF = re.compile(r"(?i)\b(?:from|join|update|into)\s+`?(\w+)`?")


def normalize(sql: str) -> str:
    return " ".join((sql or "").split()).strip()


def strip_comments(sql: str) -> str:
    return _COMMENT.sub(" ", sql)


def check_read_sql(sql: str) -> tuple[bool, str]:
    """Gate a model-supplied statement before anything touches the database."""
    if not sql or len(sql) > 2000:
        return False, "语句为空或超过 2000 字符。"
    cleaned = normalize(strip_comments(sql))
    if not cleaned:
        return False, "语句只包含注释。"
    body = cleaned.rstrip(";").strip()
    if ";" in body:
        return False, "检测到多条语句，一次只允许一条。"
    if not body.lower().startswith(READ_PREFIX):
        return False, "只允许 SELECT 读取。"
    hit = FORBIDDEN.search(body)
    if hit:
        return False, f"语句包含被禁止的关键字：{hit.group(1).upper()}。"
    tables = {t.lower() for t in _TABLE_REF.findall(body)}
    outside = tables - ALLOWED_TABLES
    if outside - {"dual"}:
        return False, f"语句引用了演示库之外的表：{', '.join(sorted(outside))}。"
    return True, body


def tables_in(sql: str) -> set[str]:
    return {t.lower() for t in _TABLE_REF.findall(normalize(strip_comments(sql)))} & ALLOWED_TABLES


class IndexGuardrails:
    """Run at stage time and again at apply time, against the live database."""

    MAX_COLUMNS = 4
    MAX_TABLE_ROWS = 5_000_000

    def __init__(self, backend):
        self.backend = backend

    def __call__(self, change) -> None:
        if change.kind != "index":
            raise ValueError(f"只接受索引类变更，收到 {change.kind}。")
        table = (change.impact.get("table") or "").lower()
        columns = [c.lower() for c in change.impact.get("columns", [])]
        if table not in ALLOWED_TABLES:
            raise ValueError(f"表 {table} 不在演示库白名单内。")
        if not (1 <= len(columns) <= self.MAX_COLUMNS):
            raise ValueError(f"索引列数量需在 1-{self.MAX_COLUMNS} 之间。")
        stats = self.backend.get_table_info(table)
        if stats["rows"] > self.MAX_TABLE_ROWS:
            raise ValueError(f"表 {table} 有 {stats['rows']:,} 行，超过演示上限，请人工处理。")
        for column in columns:
            if column not in stats["columns"]:
                raise ValueError(f"列 {table}.{column} 不存在。")
        for name, defn in stats["indexes"].items():
            if [c.lower() for c in defn] == columns:
                raise ValueError(f"已存在覆盖相同列的索引 {name}({','.join(defn)})，无需重复创建。")
        if not change.sql.upper().startswith(f"ALTER TABLE `{table.upper()}` ADD INDEX"):
            raise ValueError("变更 SQL 与登记内容不符，已拒绝。")
