#!/usr/bin/env bash
# 一键启动：检查演示库 → 起 API（自带控制台）
set -e
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3.12 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

echo "== 检查演示库 =="
.venv/bin/python - <<'EOF'
import os
from dotenv import load_dotenv
load_dotenv()
import pymysql
try:
    c = pymysql.connect(host=os.environ.get("DB_HOST","127.0.0.1"), port=int(os.environ.get("DB_PORT","3306")),
                        user=os.environ.get("DB_USER",""), password=os.environ.get("DB_PASSWORD",""),
                        database=os.environ.get("DB_NAME","ops_demo"))
    with c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM goods")
        print("ops_demo 就绪，goods 行数:", cur.fetchone()[0])
    c.close()
except pymysql.err.MySQLError:
    print("演示库未初始化，开始播种（约 10 秒）…")
    import subprocess
    subprocess.run([".venv/bin/python", "seed.py"], check=True)
EOF

echo "== 启动 API + 控制台 (http://localhost:8800) =="
exec .venv/bin/uvicorn server.app:app --host 127.0.0.1 --port 8800
