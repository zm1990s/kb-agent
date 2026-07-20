"""定时任务 API 路由（仅 chatplus 权限用户可用）。"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user
from app.models.auth import User
from app.schemas.scheduled_task import (
    ScheduledTaskCreate,
    ScheduledTaskPublic,
    ScheduledTaskUpdate,
)
from app.services import scheduled_task_service

router = APIRouter(prefix="/scheduled-tasks", tags=["scheduled-tasks"])


async def _require_chatplus(session: AsyncSession, user: User) -> None:
    """要求用户有 chatplus 模块权限（≥read）；admin 绕过。"""
    if user.role == "admin":
        return
    from app.services.rbac_service import effective_permissions

    perms = await effective_permissions(session, user=user)
    if perms.get("chatplus", "none") == "none":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "需要 chatplus 权限")


@router.get("", response_model=list[ScheduledTaskPublic])
async def list_scheduled_tasks(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[ScheduledTaskPublic]:
    await _require_chatplus(session, current_user)
    tasks = await scheduled_task_service.list_tasks(session, user_id=current_user.id)
    return [ScheduledTaskPublic.model_validate(t) for t in tasks]


@router.post("", response_model=ScheduledTaskPublic, status_code=status.HTTP_201_CREATED)
async def create_scheduled_task(
    body: ScheduledTaskCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ScheduledTaskPublic:
    await _require_chatplus(session, current_user)
    task = await scheduled_task_service.create_task(
        session,
        user_id=current_user.id,
        name=body.name,
        enabled=body.enabled,
        schedule_type=body.schedule_type,
        interval_minutes=body.interval_minutes,
        daily_hour=body.daily_hour,
        daily_minute=body.daily_minute,
        week_day=body.week_day,
        month_day=body.month_day,
        system_prompt=body.system_prompt,
        initial_message=body.initial_message,
        skill_ids=body.skill_ids,
        workspace_id=body.workspace_id,
        locale=body.locale,
    )
    return ScheduledTaskPublic.model_validate(task)


@router.get("/{task_id}", response_model=ScheduledTaskPublic)
async def get_scheduled_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ScheduledTaskPublic:
    await _require_chatplus(session, current_user)
    task = await scheduled_task_service.get_task(session, task_id=task_id, user_id=current_user.id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "定时任务不存在")
    return ScheduledTaskPublic.model_validate(task)


@router.patch("/{task_id}", response_model=ScheduledTaskPublic)
async def update_scheduled_task(
    task_id: uuid.UUID,
    body: ScheduledTaskUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ScheduledTaskPublic:
    await _require_chatplus(session, current_user)
    task = await scheduled_task_service.get_task(session, task_id=task_id, user_id=current_user.id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "定时任务不存在")
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    task = await scheduled_task_service.update_task(session, task=task, **updates)
    return ScheduledTaskPublic.model_validate(task)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_task(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    await _require_chatplus(session, current_user)
    task = await scheduled_task_service.get_task(session, task_id=task_id, user_id=current_user.id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "定时任务不存在")
    await scheduled_task_service.delete_task(session, task=task)


@router.post("/{task_id}/run", response_model=ScheduledTaskPublic)
async def run_scheduled_task_now(
    task_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ScheduledTaskPublic:
    """立即触发一次定时任务（调试用）。"""
    await _require_chatplus(session, current_user)
    task = await scheduled_task_service.get_task(session, task_id=task_id, user_id=current_user.id)
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "定时任务不存在")
    await scheduled_task_service.run_task(session, task)
    await session.refresh(task)
    return ScheduledTaskPublic.model_validate(task)
