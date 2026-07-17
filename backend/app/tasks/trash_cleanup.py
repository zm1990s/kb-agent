"""回收站清理定时任务：每 24 小时物理删除超过保留期（默认 30 天）的软删文档。"""

import asyncio
import logging

from app.core.db import SessionLocal
from app.services.document_service import purge_expired_trash

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SEC = 86400  # 每 24 小时运行一次


async def start_trash_cleanup_loop() -> None:
    """后台循环：每 24 小时清理一次过期回收站文档。"""
    logger.info("trash cleanup loop started interval=%ds", CLEANUP_INTERVAL_SEC)
    while True:
        try:
            async with SessionLocal() as session:
                count = await purge_expired_trash(session)
            logger.info("trash cleanup done purged=%d", count)
        except Exception:
            logger.exception("trash cleanup loop unexpected error")
        await asyncio.sleep(CLEANUP_INTERVAL_SEC)
