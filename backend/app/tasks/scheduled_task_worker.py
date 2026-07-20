"""定时任务后台 Worker：每分钟轮询到期任务并执行。"""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.scheduled_task import ScheduledTask

logger = logging.getLogger(__name__)

POLL_INTERVAL_SEC = 60


async def start_scheduled_task_loop() -> None:
    logger.info("scheduled_task loop started interval=%ds", POLL_INTERVAL_SEC)
    while True:
        try:
            async with SessionLocal() as session:
                now = datetime.now(UTC)
                result = await session.execute(
                    select(ScheduledTask).where(
                        ScheduledTask.enabled == True,  # noqa: E712
                        ScheduledTask.next_run_at <= now,
                    )
                )
                due_tasks = list(result.scalars().all())

            for task in due_tasks:
                try:
                    from app.services.scheduled_task_service import run_task

                    async with SessionLocal() as session:
                        live = await session.get(ScheduledTask, task.id)
                        if live and live.enabled:
                            await run_task(session, live)
                except Exception:
                    logger.exception("scheduled_task execution failed id=%s", task.id)

        except Exception:
            logger.exception("scheduled_task loop error")

        await asyncio.sleep(POLL_INTERVAL_SEC)
