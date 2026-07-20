"""定时任务业务逻辑。"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheduled_task import ScheduledTask

logger = logging.getLogger(__name__)

TITLE_PREFIX: dict[str, str] = {
    "zh": "[定时任务]",
    "zh-TW": "[定時任務]",
    "en": "[Scheduled Task]",
    "ja": "[スケジュールタスク]",
    "ko": "[예약 작업]",
}


def _title_prefix(locale: str) -> str:
    return TITLE_PREFIX.get(locale, TITLE_PREFIX["zh"])


def compute_next_run(task: ScheduledTask) -> datetime:
    """计算任务的下次执行时间（UTC）。"""
    now = datetime.now(UTC)
    if task.schedule_type == "interval":
        minutes = task.interval_minutes or 5
        return now + timedelta(minutes=minutes)
    # daily 模式
    hour = task.daily_hour or 0
    minute = task.daily_minute or 0
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


async def run_task(session: AsyncSession, task: ScheduledTask) -> None:
    """执行一次定时任务：创建 chatplus 会话，发起 LLM 调用，保存结果。"""
    from sqlalchemy import select as sa_select

    from app.engine.base import get_engine
    from app.models.auth import User
    from app.models.chat import Conversation, Message
    from app.models.skill import Skill
    from app.services.skill_service import check_skill_access

    # 加载用户
    user = await session.get(User, task.user_id)
    if user is None or not user.is_active:
        logger.warning("scheduled_task user not found or inactive task=%s", task.id)
        return

    # 构建 Skill system prompt（仿 answer_service_plus）
    skill_system: str | None = task.system_prompt
    if task.skill_ids:
        skills_result = await session.execute(
            sa_select(Skill).where(Skill.id.in_(task.skill_ids))
        )
        skill_objs = []
        for s in skills_result.scalars().all():
            if await check_skill_access(session, user=user, skill=s, level="read"):
                skill_objs.append(s)
        if skill_objs:
            sections = [f"### {s.name}\n{s.content}" for s in skill_objs]
            skills_block = "## Active Skills\n" + "\n---\n".join(sections)
            skill_system = (
                skills_block
                if skill_system is None
                else f"{skill_system}\n\n---\n\n{skills_block}"
            )

    # 创建会话（标题固定，不走 LLM 生成）
    prefix = _title_prefix(task.locale)
    title = f"{prefix}-{task.name}"[:200]
    conv = Conversation(
        id=uuid.uuid4(),
        workspace_id=task.workspace_id,
        user_id=task.user_id,
        title=title,
        source="chatplus",
    )
    session.add(conv)
    await session.flush()

    # 保存用户消息
    session.add(Message(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        role="user",
        content=task.initial_message,
        sources=[],
        attachments=[],
        output_files=[],
    ))
    await session.flush()

    # 调用 engine（同步等待，后台静默）
    try:
        engine = get_engine("claude_cli", audit_user=user.email)
        result = await engine.complete(task.initial_message, system=skill_system)
        answer = result.text.strip() if result.text else "(无输出)"
    except Exception:
        logger.exception("scheduled_task engine error task=%s conv=%s", task.id, conv.id)
        answer = "(执行失败，请查看日志)"

    # 保存助手回复
    session.add(Message(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        role="assistant",
        content=answer,
        sources=[],
        attachments=[],
        output_files=[],
    ))

    # 更新任务执行时间
    task.last_run_at = datetime.now(UTC)
    task.next_run_at = compute_next_run(task)
    session.add(task)
    await session.commit()
    logger.info("scheduled_task done task=%s conv=%s", task.id, conv.id)


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def create_task(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    enabled: bool,
    schedule_type: str,
    interval_minutes: int | None,
    daily_hour: int | None,
    daily_minute: int | None,
    system_prompt: str | None,
    initial_message: str,
    skill_ids: list[uuid.UUID],
    workspace_id: uuid.UUID | None,
    locale: str,
) -> ScheduledTask:
    task = ScheduledTask(
        id=uuid.uuid4(),
        user_id=user_id,
        name=name,
        enabled=enabled,
        schedule_type=schedule_type,
        interval_minutes=interval_minutes,
        daily_hour=daily_hour,
        daily_minute=daily_minute,
        system_prompt=system_prompt,
        initial_message=initial_message,
        skill_ids=skill_ids,
        workspace_id=workspace_id,
        locale=locale,
    )
    task.next_run_at = compute_next_run(task) if enabled else None
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def get_task(
    session: AsyncSession, *, task_id: uuid.UUID, user_id: uuid.UUID
) -> ScheduledTask | None:
    task = await session.get(ScheduledTask, task_id)
    if task is None or task.user_id != user_id:
        return None
    return task


async def list_tasks(
    session: AsyncSession, *, user_id: uuid.UUID
) -> list[ScheduledTask]:
    result = await session.execute(
        select(ScheduledTask)
        .where(ScheduledTask.user_id == user_id)
        .order_by(ScheduledTask.created_at.desc())
    )
    return list(result.scalars().all())


async def update_task(
    session: AsyncSession,
    *,
    task: ScheduledTask,
    **kwargs,
) -> ScheduledTask:
    for key, val in kwargs.items():
        if val is not None or key in ("system_prompt", "workspace_id"):
            setattr(task, key, val)
    # 重新计算下次执行时间
    if task.enabled:
        task.next_run_at = compute_next_run(task)
    else:
        task.next_run_at = None
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


async def delete_task(session: AsyncSession, *, task: ScheduledTask) -> None:
    await session.delete(task)
    await session.commit()
