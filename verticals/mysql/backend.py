"""Every database read and write the MySQL agent can reach, behind real connections."""

from __future__ import annotations

import time

from ops_common.db import connect, dbname, fetch_all


class MysqlBackend:
    DEMO_TABLES = ("goods", "orders", "search_log")

    # The demo's built-in slow query: "my orders" filters user_id with no index on it.
    SAMPLE_SLOW_SQL = (
        "SELECT id, total, status, created_at FROM orders "
        "WHERE user_id = 42 ORDER BY created_at DESC LIMIT 10"
    )

    # -- reads used by tools -------------------------------------------------

    def get_slow_queries(self, limit: int = 5) -> list[dict]:
        rows = fetch_all(
            """
            SELECT DIGEST_TEXT                          AS digest,
                   COUNT_STAR                           AS count_star,
                   ROUND(SUM_TIMER_WAIT/1e12, 2)        AS total_sec,
                   ROUND(AVG_TIMER_WAIT/1e9, 1)         AS avg_ms,
                   CAST(SUM_ROWS_EXAMINED/COUNT_STAR AS UNSIGNED) AS rows_examined,
                   LEFT(QUERY_SAMPLE_TEXT, 240)         AS sample_text
            FROM performance_schema.events_statements_summary_by_digest
            WHERE SCHEMA_NAME = %s AND DIGEST_TEXT LIKE 'SELECT%%'
            ORDER BY SUM_TIMER_WAIT DESC
            LIMIT %s
            """,
            (dbname(), int(limit)),
            db="performance_schema",
        )
        for row in rows:
            row["digest"] = " ".join(str(row["digest"]).split())
            row["sample_text"] = " ".join(str(row["sample_text"] or "").split())
        return rows

    def get_table_info(self, table: str) -> dict:
        stats = fetch_all(
            """
            SELECT TABLE_ROWS, ROUND((DATA_LENGTH+INDEX_LENGTH)/1048576, 1) AS size_mb, ENGINE
            FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            """,
            (dbname(), table),
        )
        if not stats:
            raise ValueError(f"表 {table} 不存在")
        columns = fetch_all(
            """
            SELECT COLUMN_NAME, COLUMN_TYPE FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION
            """,
            (dbname(), table),
        )
        with connect(dbname()) as conn, conn.cursor() as cur:
            cur.execute(f"SHOW INDEX FROM `{table}`")
            raw_indexes = list(cur.fetchall())
        indexes: dict[str, list[str]] = {}
        for row in raw_indexes:
            indexes.setdefault(row["Key_name"], []).append(row["Column_name"])
        return {
            "table": table,
            "rows": int(stats[0]["TABLE_ROWS"] or 0),
            "size_mb": float(stats[0]["size_mb"] or 0),
            "engine": stats[0]["ENGINE"],
            "columns": {row["COLUMN_NAME"]: row["COLUMN_TYPE"] for row in columns},
            "indexes": indexes,
        }

    def explain(self, sql: str) -> str:
        with connect(dbname()) as conn, conn.cursor() as cur:
            cur.execute(f"EXPLAIN FORMAT=TREE {sql}")
            row = cur.fetchone()
        return next(iter(row.values())).strip() if row else ""

    def measure(self, sql: str, cap_ms: int = 2000, row_cap: int = 50) -> dict:
        """Run a gated SELECT once, timed, with a session-level execution cap."""
        with connect(dbname()) as conn, conn.cursor() as cur:
            cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(cap_ms)}")
            started = time.perf_counter()
            cur.execute(sql)
            rows = cur.fetchmany(row_cap + 1)[:row_cap]
            elapsed_ms = (time.perf_counter() - started) * 1000
        return {"elapsed_ms": round(elapsed_ms, 1), "rows": [[str(v) for v in r.values()] for r in rows]}

    # -- the single write path (called only by the approve route) ------------

    def apply_ddl(self, sql: str) -> None:
        with connect(dbname()) as conn, conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()

    def server_version(self) -> str:
        row = fetch_all("SELECT VERSION() AS v")
        return row[0]["v"]
