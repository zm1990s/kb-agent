"""用量事件记录与统计。"""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
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
    since = datetime.utcnow() - timedelta(days=days)

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

    # 按用户 + action 聚合（JOIN users 取邮箱，NULL user_id 归入"匿名"）
    user_rows = await session.execute(
        select(
            UsageEvent.user_id,
            User.email,
            UsageEvent.action,
            func.count().label("cnt"),
        )
        .outerjoin(User, UsageEvent.user_id == User.id)
        .where(UsageEvent.created_at >= since)
        .group_by(UsageEvent.user_id, User.email, UsageEvent.action)
        .order_by(User.email, UsageEvent.action)
    )
    # 合并成 [{email, login, upload, chat, download, total}, ...]
    user_map: dict[str, dict] = {}
    for r in user_rows:
        key = r.email or "(匿名)"
        if key not in user_map:
            user_map[key] = {"email": key, "login": 0, "upload": 0, "chat": 0, "download": 0}
        if r.action in user_map[key]:
            user_map[key][r.action] = r.cnt
    per_user = sorted(
        [{"total": sum(v for k, v in u.items() if k != "email"), **u} for u in user_map.values()],
        key=lambda u: u["total"],
        reverse=True,
    )

    return {"days": days, "daily": daily, "active_users": active_users, "totals": totals, "per_user": per_user}
