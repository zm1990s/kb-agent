"""聊天+ 文件清理定时任务：每 24 小时删除超过保留期的会话文件。

保留天数由管理员在系统设置中配置（chat_file_retention_days，默认 30）。
"""

import asyncio
import logging

from app.core.db import SessionLocal
from app.services.chat_file_service import purge_expired_chat_files
from app.services.settings_service import get_chat_file_retention_days

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SEC = 86400  # 每 24 小时运行一次


async def start_chat_file_cleanup_loop() -> None:
    """后台循环：每 24 小时按保留期清理一次聊天+ 会话文件。"""
    logger.info("chat file cleanup loop started interval=%ds", CLEANUP_INTERVAL_SEC)
    while True:
        try:
            async with SessionLocal() as session:
                days = await get_chat_file_retention_days(session)
                count = await purge_expired_chat_files(session, retention_days=days)
            logger.info("chat file cleanup done purged=%d retention=%dd", count, days)
        except Exception:
            logger.exception("chat file cleanup loop unexpected error")
        await asyncio.sleep(CLEANUP_INTERVAL_SEC)
