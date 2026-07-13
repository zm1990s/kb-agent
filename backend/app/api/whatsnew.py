"""新动态路由。"""

import asyncio
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.core.deps import get_current_user, require_admin
from app.models.auth import User
from app.services.whatsnew_service import get_latest_reports_for_user
from app.services.whatsnew_subscription_service import (
    FREQ_DAYS,
    delete_subscription,
    get_subscription,
    upsert_subscription,
)
from app.tasks.whatsnew_worker import run_all_workspaces

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/whatsnew", tags=["whatsnew"])

_background_tasks: set[asyncio.Task] = set()


@router.get("")
async def get_whatsnew(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """返回当前用户可见空间的最新新动态报告。"""
    return await get_latest_reports_for_user(session, user=current_user)


@router.post("/trigger", status_code=202)
async def trigger_whatsnew(
    background_tasks: BackgroundTasks,
    _admin: User = Depends(require_admin),
) -> dict[str, str]:
    """管理员手动触发全量摘要生成（异步后台执行）。"""
    logger.info("whatsnew manual trigger by admin=%s", _admin.id)
    task = asyncio.create_task(run_all_workspaces())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return {"status": "triggered"}


# ── 邮件订阅 ─────────────────────────────────────────────────


class SubscriptionIn(BaseModel):
    frequency: str  # weekly / biweekly / monthly


class SubscriptionOut(BaseModel):
    email: str
    frequency: str
    last_sent_at: str | None
    created_at: str


@router.get("/subscription", response_model=SubscriptionOut)
async def get_subscription_endpoint(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionOut:
    sub = await get_subscription(session, user_id=current_user.id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "尚未订阅")
    return SubscriptionOut(
        email=current_user.email,
        frequency=sub.frequency,
        last_sent_at=sub.last_sent_at.isoformat() if sub.last_sent_at else None,
        created_at=sub.created_at.isoformat(),
    )


@router.put("/subscription", response_model=SubscriptionOut)
async def upsert_subscription_endpoint(
    body: SubscriptionIn,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionOut:
    if body.frequency not in FREQ_DAYS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"frequency 须为 {list(FREQ_DAYS.keys())} 之一",
        )
    sub = await upsert_subscription(
        session, user_id=current_user.id, frequency=body.frequency
    )
    return SubscriptionOut(
        email=current_user.email,
        frequency=sub.frequency,
        last_sent_at=sub.last_sent_at.isoformat() if sub.last_sent_at else None,
        created_at=sub.created_at.isoformat(),
    )


@router.delete("/subscription", status_code=status.HTTP_204_NO_CONTENT)
async def delete_subscription_endpoint(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    ok = await delete_subscription(session, user_id=current_user.id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "尚未订阅")
