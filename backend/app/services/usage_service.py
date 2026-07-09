"""用量事件记录与统计。"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage import UsageEvent


async def record_event(
    session: AsyncSession,
    *,
    action: str,
    user_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    meta: dict | None = None,
) -> None:
    """记录一条用量事件（忽略异常，不影响主流程）。"""
    try:
        session.add(
            UsageEvent(
                user_id=user_id,
                workspace_id=workspace_id,
                action=action,
                meta=meta or {},
            )
        )
        await session.commit()
    except Exception:
        await session.rollback()


async def get_stats(session: AsyncSession, days: int = 30) -> dict:
    """返回近 N 天的统计数据，供报表页使用。"""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # 按天 + action 聚合
    rows = await session.execute(
        select(
            func.date_trunc("day", UsageEvent.created_at).label("day"),
            UsageEvent.action,
            func.count().label("cnt"),
        )
        .where(UsageEvent.created_at >= since)
        .group_by(text("1"), UsageEvent.action)
        .order_by(text("1"))
    )
    daily: list[dict] = [
        {"day": r.day.strftime("%Y-%m-%d"), "action": r.action, "count": r.cnt}
        for r in rows
    ]

    # 活跃用户（按天去重）
    au_rows = await session.execute(
        select(
            func.date_trunc("day", UsageEvent.created_at).label("day"),
            func.count(func.distinct(UsageEvent.user_id)).label("users"),
        )
        .where(UsageEvent.created_at >= since, UsageEvent.user_id.is_not(None))
        .group_by(text("1"))
        .order_by(text("1"))
    )
    active_users: list[dict] = [
        {"day": r.day.strftime("%Y-%m-%d"), "users": r.users} for r in au_rows
    ]

    # 总计
    totals_rows = await session.execute(
        select(UsageEvent.action, func.count().label("cnt"))
        .where(UsageEvent.created_at >= since)
        .group_by(UsageEvent.action)
    )
    totals = {r.action: r.cnt for r in totals_rows}

    return {"days": days, "daily": daily, "active_users": active_users, "totals": totals}
