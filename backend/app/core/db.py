"""数据库连接：async engine + session 依赖 + ORM Base。

M0 阶段只建立连接设施，不定义任何业务表（表交给 M1/M2）。
"""

import logging
from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类（业务模型在 M1/M2 定义）。"""


_settings = get_settings()

engine = create_async_engine(_settings.database_url, echo=False, pool_pre_ping=True)

SessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：产出一个 async 数据库会话。"""
    async with SessionLocal() as session:
        yield session


async def run_migrations() -> None:
    """按序执行 infra/postgres/migrations/ 下所有 SQL 迁移文件（幂等）。

    所有迁移均使用 CREATE TABLE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS，
    可安全地在每次启动时重复执行。
    """
    migrations_dir = Path(__file__).parent.parent.parent / "infra" / "postgres" / "migrations"
    if not migrations_dir.exists():
        logger.warning("迁移目录不存在，跳过: %s", migrations_dir)
        return

    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        logger.warning("未找到迁移文件: %s", migrations_dir)
        return

    async with engine.connect() as conn:
        # 获取底层 asyncpg 连接，它支持一次执行含多条语句的 SQL 块
        raw = await conn.get_raw_connection()
        asyncpg_conn = raw.driver_connection
        for sql_file in sql_files:
            sql = sql_file.read_text(encoding="utf-8")
            try:
                await asyncpg_conn.execute(sql)
                logger.debug("迁移完成: %s", sql_file.name)
            except Exception:
                logger.exception("迁移失败: %s", sql_file.name)
                raise

    logger.info("数据库迁移完成，共 %d 个文件", len(sql_files))
