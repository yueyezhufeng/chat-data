# ops-agents demo database seeder.
#
# Creates the ops_demo schema with a deliberately un-tuned shop:
#   goods      500k rows, searched with a non-indexable leading-wildcard LIKE
#   orders     200k rows, "my orders" query filters user_id with NO index on it
#   search_log every storefront search / order lookup is timed and logged here
# Demo queries are pre-run so performance_schema digests have data on first start.
#
# Idempotent: drops and recreates ONLY the three tables inside ops_demo.

import os
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

import pymysql
from dotenv import load_dotenv

load_dotenv()

DB = dict(
    host=os.environ.get("DB_HOST", "127.0.0.1"),
    port=int(os.environ.get("DB_PORT", "3306")),
    user=os.environ.get("DB_USER", ""),
    password=os.environ.get("DB_PASSWORD", ""),
    dbname=os.environ.get("DB_NAME", "ops_demo"),
)

GOODS_ROWS = 500_000
ORDER_ROWS = 200_000
USERS = 8_000

BRANDS = ["山岳", "云杉", "北纬", "白鲸", "晨光", "铁星", "青竹", "橙子", "大熊", "简一"]
ITEMS = {  # 品名 → 所属类目（保持一致，演示截图才像真的）
    "双人帐篷": "户外露营", "露营灯": "户外露营", "睡袋": "户外露营", "冲锋衣": "户外露营",
    "便携椅": "户外露营", "防水袋": "户外露营", "露营桌": "户外露营",
    "保温杯": "家居厨房", "空气炸锅": "家居厨房", "榨汁机": "家居厨房", "加湿器": "家居厨房",
    "记忆枕": "家居厨房", "咖啡手冲壶": "家居厨房",
    "电动牙刷": "美妆个护", "洗发水": "美妆个护",
    "蓝牙耳机": "数码配件", "机械键盘": "数码配件", "行车记录仪": "数码配件",
    "瑜伽垫": "运动健身", "跑鞋": "运动健身", "哑铃": "运动健身",
    "积木套装": "儿童玩具", "猫粮": "宠物用品", " Notebook 笔记本": "图书文具",
}
WORDS = ["帐篷", "露营", "保温", "耳机", "瑜伽", "猫", "键盘", "跑鞋", "露营灯", "榨汁", "枕头", "冲锋衣"]


def conn(db: str | None = None) -> pymysql.connections.Connection:
    return pymysql.connect(
        host=DB["host"], port=DB["port"], user=DB["user"], password=DB["password"],
        database=db, charset="utf8mb4", autocommit=False,
    )


def create_schema() -> None:
    with conn() as c, c.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {DB['dbname']} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.execute(f"USE {DB['dbname']}")
        cur.execute("DROP TABLE IF EXISTS search_log")
        cur.execute("DROP TABLE IF EXISTS orders")
        cur.execute("DROP TABLE IF EXISTS goods")
        cur.execute(
            """CREATE TABLE goods (
                 id BIGINT PRIMARY KEY AUTO_INCREMENT,
                 name VARCHAR(180) NOT NULL,
                 category VARCHAR(40) NOT NULL,
                 price DECIMAL(10,2) NOT NULL,
                 stock INT NOT NULL,
                 sales_30d INT NOT NULL,
                 status VARCHAR(10) NOT NULL DEFAULT 'active'
               ) ENGINE=InnoDB"""
        )
        cur.execute(
            """CREATE TABLE orders (
                 id BIGINT PRIMARY KEY AUTO_INCREMENT,
                 user_id INT NOT NULL,
                 total DECIMAL(10,2) NOT NULL,
                 status VARCHAR(16) NOT NULL,
                 channel VARCHAR(16) NOT NULL,
                 created_at DATETIME NOT NULL
               ) ENGINE=InnoDB"""
        )
        # Deliberately NO index on orders.user_id / goods(category): the demo's whole point.
        cur.execute(
            """CREATE TABLE search_log (
                 id BIGINT PRIMARY KEY AUTO_INCREMENT,
                 keyword VARCHAR(120) NOT NULL,
                 latency_ms INT NOT NULL,
                 hits INT NOT NULL,
                 source VARCHAR(20) NOT NULL,
                 created_at DATETIME NOT NULL
               ) ENGINE=InnoDB"""
        )
        c.commit()
    print(f"schema ready: {DB['dbname']}")


def goods_row(rng: random.Random) -> tuple:
    item = rng.choice(list(ITEMS))
    name = f"{rng.choice(BRANDS)} {item} {rng.choice(['标准版', 'Pro', '升级款', '经典款', '迷你款', '2026款'])}"
    return (
        name, ITEMS[item],
        round(rng.uniform(19.9, 2999.0), 2), rng.randint(0, 500), rng.randint(0, 3000),
        "active" if rng.random() > 0.05 else "paused",
    )


def seed_goods() -> None:
    rng = random.Random(42)
    started = time.time()
    with conn(DB["dbname"]) as c, c.cursor() as cur:
        batch: list[tuple] = []
        sql = "INSERT INTO goods (name, category, price, stock, sales_30d, status) VALUES (%s,%s,%s,%s,%s,%s)"
        for i in range(1, GOODS_ROWS + 1):
            batch.append(goods_row(rng))
            if len(batch) >= 5000:
                cur.executemany(sql, batch)
                c.commit()
                batch = []
        if batch:
            cur.executemany(sql, batch)
            c.commit()
    print(f"goods: {GOODS_ROWS} rows in {time.time()-started:.1f}s")


def seed_orders() -> None:
    rng = random.Random(7)
    started = time.time()
    now = datetime.now()
    with conn(DB["dbname"]) as c, c.cursor() as cur:
        batch: list[tuple] = []
        sql = "INSERT INTO orders (user_id, total, status, channel, created_at) VALUES (%s,%s,%s,%s,%s)"
        for _ in range(ORDER_ROWS):
            dt = now - timedelta(minutes=rng.randint(0, 60 * 24 * 30))
            batch.append((
                rng.randint(1, USERS), round(rng.uniform(29, 4800), 2),
                rng.choices(["delivered", "shipped", "processing", "cancelled"], weights=[6, 2, 1, 1])[0],
                rng.choice(["storefront", "app", "miniapp"]), dt,
            ))
            if len(batch) >= 5000:
                cur.executemany(sql, batch)
                c.commit()
                batch = []
        if batch:
            cur.executemany(sql, batch)
            c.commit()
    print(f"orders: {ORDER_ROWS} rows in {time.time()-started:.1f}s")


def seed_search_log() -> None:
    rng = random.Random(11)
    now = datetime.now()
    rows: list[tuple] = []
    for hours_ago in range(47, -1, -1):
        # baseline 40-120ms; the last 3 hours carry the incident spike (missing index hit by traffic)
        spike = hours_ago <= 3
        for _ in range(rng.randint(8, 20)):
            kw = rng.choice(WORDS)
            ms = rng.randint(600, 1400) if spike else rng.randint(35, 130)
            rows.append((kw, ms, rng.randint(0, 400), "storefront", now - timedelta(hours=hours_ago, minutes=rng.randint(0, 59))))
    with conn(DB["dbname"]) as c, c.cursor() as cur:
        cur.executemany(
            "INSERT INTO search_log (keyword, latency_ms, hits, source, created_at) VALUES (%s,%s,%s,%s,%s)",
            rows,
        )
        c.commit()
    print(f"search_log: {len(rows)} rows")


def warm_digests() -> None:
    """Run the demo's slow queries a few times so performance_schema digests exist."""
    started = time.time()
    with conn(DB["dbname"]) as c, c.cursor() as cur:
        cur.execute("SELECT id,total,status,created_at FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 10")
        cur.fetchall()
        cur.execute("SELECT id,name,category,price,stock,sales_30d FROM goods WHERE category = '户外露营' AND name LIKE '%帐篷%' ORDER BY sales_30d DESC LIMIT 12")
        cur.fetchall()
        c.commit()
    print(f"digests warmed in {time.time()-started:.1f}s")


if __name__ == "__main__":
    t0 = time.time()
    changes_file = Path(__file__).parent / "data" / "mysql_changes.json"
    if changes_file.exists():
        changes_file.unlink()
        print("cleared staged-change history")
    create_schema()
    seed_goods()
    seed_orders()
    seed_search_log()
    warm_digests()
    print(f"seed complete in {time.time()-t0:.1f}s")
