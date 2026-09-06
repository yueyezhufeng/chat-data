"""MySQL connection helper. Per-call connections: the demo DB is local."""

from __future__ import annotations

import os

import pymysql
import pymysql.cursors


def _settings() -> dict:
    return dict(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", ""),
        password=os.environ.get("DB_PASSWORD", ""),
        charset="utf8mb4",
        connect_timeout=5,
        cursorclass=pymysql.cursors.DictCursor,
    )


def dbname() -> str:
    return os.environ.get("DB_NAME", "ops_demo")


def connect(db: str | None = None) -> pymysql.connections.Connection:
    return pymysql.connect(database=db if db is not None else dbname(), **_settings())


def fetch_all(sql: str, args: tuple = (), db: str | None = None) -> list[dict]:
    with connect(db) as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())
