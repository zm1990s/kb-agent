"""What's New 邮件订阅业务逻辑。"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.whatsnew_subscription import WhatsNewSubscription

FrequencyType = Literal["weekly", "biweekly", "monthly"]

FREQ_DAYS: dict[str, int] = {
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
}


async def get_subscription(
    session: AsyncSession, *, user_id: uuid.UUID
) -> WhatsNewSubscription | None:
    result = await session.execute(
        select(WhatsNewSubscription).where(WhatsNewSubscription.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def upsert_subscription(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    frequency: str,
) -> WhatsNewSubscription:
    existing = await get_subscription(session, user_id=user_id)
    if existing is not None:
        existing.frequency = frequency
        await session.commit()
        await session.refresh(existing)
        return existing
    sub = WhatsNewSubscription(user_id=user_id, frequency=frequency)
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def delete_subscription(
    session: AsyncSession, *, user_id: uuid.UUID
) -> bool:
    sub = await get_subscription(session, user_id=user_id)
    if sub is None:
        return False
    await session.delete(sub)
    await session.commit()
    return True


async def get_due_subscriptions(
    session: AsyncSession,
) -> list[WhatsNewSubscription]:
    """返回所有"到期需发送"的订阅。"""
    result = await session.execute(select(WhatsNewSubscription))
    all_subs = list(result.scalars().all())
    now = datetime.now(UTC)
    due = []
    for sub in all_subs:
        days = FREQ_DAYS.get(sub.frequency, 7)
        if sub.last_sent_at is None:
            due.append(sub)
        else:
            last = (
                sub.last_sent_at.replace(tzinfo=UTC)
                if sub.last_sent_at.tzinfo is None
                else sub.last_sent_at
            )
            if now - last >= timedelta(days=days):
                due.append(sub)
    return due


async def mark_sent(
    session: AsyncSession, *, sub: WhatsNewSubscription
) -> None:
    sub.last_sent_at = datetime.now(UTC)
    await session.commit()
