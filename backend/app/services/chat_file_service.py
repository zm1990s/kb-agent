"""聊天+ 会话文件保留期清理。

按文件 mtime 判断到期（每个文件从它最后修改起算 retention_days）。
仅处理 source='chatplus' 的会话目录 chatplus/conv_{conversation_id}/（与工作区解耦）。
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Conversation
from app.storage.base import get_storage

logger = logging.getLogger(__name__)


async def purge_expired_chat_files(
    session: AsyncSession, *, retention_days: int
) -> int:
    """删除所有聊天+ 会话目录中 mtime 超过保留期的文件。返回删除文件数。"""
    cutoff = time.time() - retention_days * 86400
    storage = get_storage()

    result = await session.execute(
        select(Conversation.id).where(Conversation.source == "chatplus")
    )
    conv_ids = [row[0] for row in result.all()]

    deleted = 0
    for conv_id in conv_ids:
        prefix = f"chatplus/conv_{conv_id}"
        try:
            files = await storage.stat_files(prefix)
        except Exception:  # noqa: BLE001
            logger.warning("stat_files 失败 prefix=%s", prefix, exc_info=True)
            continue
        for f in files:
            if f["mtime"] < cutoff:
                try:
                    await storage.delete(f["key"])
                    deleted += 1
                except FileNotFoundError:
                    pass
                except Exception:  # noqa: BLE001
                    logger.warning("删除过期文件失败 key=%s", f["key"], exc_info=True)
    return deleted
