"""The shop's real backend: every query is timed and logged, which is what feeds both
the storefront's latency badges and the MySQL agent's diagnosis material."""

from __future__ import annotations

import time

from ops_common.db import connect, dbname, fetch_all


class CommerceBackend:
    def search_goods(self, keyword: str, category: str | None = None, limit: int = 12) -> dict:
        keyword = f"%{keyword.strip()}%"
        sql = (
            "SELECT id, name, category, price, stock, sales_30d FROM goods "
            "WHERE status = 'active' AND (name LIKE %s OR category LIKE %s) "
        )
        args: list = [keyword, keyword]
        if category:
            sql += "AND category = %s "
            args.append(category)
        sql += "ORDER BY sales_30d DESC LIMIT %s"
        args.append(int(limit))
        rows, elapsed_ms = self._timed(sql, tuple(args))
        self._log("search", elapsed_ms, len(rows))
        return {"rows": rows, "elapsed_ms": elapsed_ms, "keyword": keyword.strip("%")}

    def get_product(self, product_id: int) -> dict | None:
        rows = fetch_all(
            "SELECT id, name, category, price, stock, sales_30d FROM goods WHERE id = %s",
            (product_id,),
        )
        return rows[0] if rows else None

    def get_user_orders(self, user_id: int, limit: int = 10) -> dict:
        sql = (
            "SELECT id, total, status, channel, created_at FROM orders "
            "WHERE user_id = %s ORDER BY created_at DESC LIMIT %s"
        )
        rows, elapsed_ms = self._timed(sql, (int(user_id), int(limit)))
        self._log("orders", elapsed_ms, len(rows))
        return {"rows": rows, "elapsed_ms": elapsed_ms}

    def snapshot(self) -> dict:
        """Business figures over the real tables; conversion is a declared demo simulation
        of the latency → conversion link, so the story stays legible without load testing."""
        today = fetch_all(
            "SELECT COUNT(*) AS orders, IFNULL(SUM(total),0) AS revenue FROM orders WHERE created_at >= CURDATE()"
        )[0]
        latency = fetch_all(
            """
            SELECT MAX(latency_ms) AS p99, ROUND(AVG(latency_ms)) AS avg_ms
            FROM search_log WHERE created_at >= NOW() - INTERVAL 2 HOUR
            """
        )[0]
        p99 = int(latency["p99"] or 0)
        conversion = round(max(0.6, 3.4 - max(0.0, (p99 - 200) / 100 * 0.45)), 2)
        series = self.latency_series()
        return {
            "orders_today": int(today["orders"]),
            "revenue_today": float(today["revenue"]),
            "search_p99_ms": p99,
            "search_avg_ms": int(latency["avg_ms"] or 0),
            "conversion_rate": conversion,
            "db_healthy": p99 < 400,
            "series": series,
        }

    def latency_series(self, hours: int = 12) -> list[dict]:
        rows = fetch_all(
            """
            SELECT DATE_FORMAT(created_at, '%%d日%%H时') AS bucket,
                   MIN(created_at) AS ts,
                   ROUND(AVG(latency_ms)) AS avg_ms,
                   MAX(latency_ms) AS max_ms,
                   SUM(source = 'orders') AS order_lookups
            FROM search_log
            WHERE created_at >= NOW() - INTERVAL %s HOUR
            GROUP BY DATE_FORMAT(created_at, '%%d日%%H时')
            ORDER BY ts
            """,
            (hours,),
        )
        for row in rows:
            row["conversion"] = round(max(0.6, 3.4 - max(0.0, (row["max_ms"] - 200) / 100 * 0.45)), 2)
        return rows

    def recent_orders(self, limit: int = 8) -> list[dict]:
        return fetch_all(
            "SELECT id, user_id, total, status, channel, created_at FROM orders ORDER BY id DESC LIMIT %s",
            (int(limit),),
        )

    # -- helpers -------------------------------------------------------------

    def _timed(self, sql: str, args: tuple) -> tuple[list[dict], float]:
        with connect(dbname()) as conn, conn.cursor() as cur:
            started = time.perf_counter()
            cur.execute(sql, args)
            rows = list(cur.fetchall())
            elapsed_ms = (time.perf_counter() - started) * 1000
        return rows, round(elapsed_ms, 1)

    def _log(self, source: str, elapsed_ms: float, hits: int, keyword: str = "-") -> None:
        with connect(dbname()) as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO search_log (keyword, latency_ms, hits, source, created_at) "
                "VALUES (%s, %s, %s, %s, NOW())",
                (keyword, int(elapsed_ms), hits, source),
            )
            conn.commit()
