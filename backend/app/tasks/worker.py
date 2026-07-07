"""进程内后台任务调度（Q6：asyncio，不引入外部队列）。

每个任务用独立 DB 会话运行，避免复用请求作用域的会话。
重启会丢失未完成任务；靠 processing_tasks 表可查状态并 reprocess 重试。
"""

import asyncio
import uuid

from app.core.db import SessionLocal
from app.services.classify_service import run_classification


async def _run_task(task_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        await run_classification(session, task_id)


def enqueue_classification(task_id: uuid.UUID) -> None:
    """把归类任务投入事件循环后台执行（fire-and-forget）。"""
    # 保存引用避免任务被 GC；完成后自动丢弃
    task = asyncio.create_task(_run_task(task_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


_background_tasks: set[asyncio.Task] = set()
