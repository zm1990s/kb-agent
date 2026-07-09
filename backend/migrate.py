"""数据库迁移脚本：按文件名顺序执行 infra/postgres/migrations/*.sql。

使用 schema_migrations 表记录已执行的版本，幂等——多次运行只会跑未执行过的迁移。
直接用 asyncpg（不经 SQLAlchemy ORM），在 uvicorn 启动前执行。
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg


MIGRATIONS_DIR = Path(__file__).parent.parent / "infra" / "postgres" / "migrations"


async def run_migrations(dsn: str) -> None:
    # asyncpg 使用 postgresql:// scheme；SQLAlchemy 用 postgresql+asyncpg://，需转换
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)

    conn = await asyncpg.connect(dsn)
    try:
        # 建迁移版本表（首次运行时）
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)

        sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not sql_files:
            print("migrate: 未找到迁移文件，跳过", flush=True)
            return

        for sql_file in sql_files:
            filename = sql_file.name
            already = await conn.fetchval(
                "SELECT 1 FROM schema_migrations WHERE filename = $1", filename
            )
            if already:
                print(f"migrate: 跳过（已执行）{filename}", flush=True)
                continue

            sql = sql_file.read_text(encoding="utf-8")
            print(f"migrate: 执行 {filename} ...", flush=True)
            await conn.execute(sql)
            await conn.execute(
                "INSERT INTO schema_migrations(filename) VALUES($1)", filename
            )
            print(f"migrate: 完成 {filename}", flush=True)

        print("migrate: 全部迁移完成", flush=True)
    finally:
        await conn.close()


if __name__ == "__main__":
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("migrate: DATABASE_URL 未设置，退出", file=sys.stderr)
        sys.exit(1)
    asyncio.run(run_migrations(dsn))
