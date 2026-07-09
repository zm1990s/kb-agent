"""进程内后台任务调度（Q6：asyncio，不引入外部队列）。

每个任务用独立 DB 会话运行，避免复用请求作用域的会话。
重启会丢失未完成任务；靠 processing_tasks 表可查状态并 reprocess 重试。
"""

import asyncio
import logging
import uuid

from app.core.db import SessionLocal
from app.models.document import ProcessingTask
from app.services.classify_service import run_classification

logger = logging.getLogger(__name__)

# 首次重试等待秒数；后续指数退避：5s → 10s → 20s
_RETRY_BASE_DELAY = 5


async def _run_task_with_retry(task_id: uuid.UUID) -> None:
    """执行归类任务，失败后按 max_attempts 自动重试（指数退避）。"""
    retry = 0
    while True:
        async with SessionLocal() as session:
            await run_classification(session, task_id)
            task = await session.get(ProcessingTask, task_id)
            if task is None or task.status == "succeeded":
                return
            if task.attempts >= task.max_attempts:
                logger.warning(
                    "classify task %s 已达最大尝试次数 %d，停止重试",
                    task_id, task.max_attempts,
                )
                return
            delay = _RETRY_BASE_DELAY * (2 ** retry)
            logger.info(
                "classify task %s 第 %d 次失败，%ds 后自动重试…",
                task_id, task.attempts, delay,
            )

        retry += 1
        await asyncio.sleep(delay)


def enqueue_classification(task_id: uuid.UUID) -> None:
    """把归类任务投入事件循环后台执行（fire-and-forget，含自动重试）。"""
    task = asyncio.create_task(_run_task_with_retry(task_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


_background_tasks: set[asyncio.Task] = set()
