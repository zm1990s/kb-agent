"""用量事件记录与统计。"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import cast, func, select, text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import User
from app.models.document import Document
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


async def get_download_events(
    session: AsyncSession,
    days: int = 30,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    total = (
        await session.execute(
            select(func.count()).select_from(UsageEvent).where(
                UsageEvent.action == "download",
                UsageEvent.created_at >= since,
            )
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(
                UsageEvent.created_at,
                User.email,
                UsageEvent.meta["document_id"].as_string().label("document_id"),
                Document.title,
            )
            .outerjoin(User, User.id == UsageEvent.user_id)
            .outerjoin(
                Document,
                Document.id == cast(UsageEvent.meta["document_id"].as_string(), PG_UUID(as_uuid=True)),
            )
            .where(UsageEvent.action == "download", UsageEvent.created_at >= since)
            .order_by(UsageEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "total": total,
        "items": [
            {
                "created_at": r.created_at.isoformat(),
                "email": r.email or "(匿名)",
                "document_id": r.document_id,
                "document_title": r.title or "(文档已删除)",
            }
            for r in rows
        ],
    }


async def get_chat_events(
    session: AsyncSession,
    days: int = 30,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    total = (
        await session.execute(
            select(func.count()).select_from(UsageEvent).where(
                UsageEvent.action == "chat",
                UsageEvent.created_at >= since,
            )
        )
    ).scalar_one()
    rows = (
        await session.execute(
            select(
                UsageEvent.created_at,
                User.email,
                UsageEvent.meta["question"].as_string().label("question"),
                UsageEvent.meta["answer"].as_string().label("answer"),
                UsageEvent.meta["conversation_id"].as_string().label("conversation_id"),
            )
            .outerjoin(User, User.id == UsageEvent.user_id)
            .where(UsageEvent.action == "chat", UsageEvent.created_at >= since)
            .order_by(UsageEvent.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()
    return {
        "total": total,
        "items": [
            {
                "created_at": r.created_at.isoformat(),
                "email": r.email or "(匿名)",
                "conversation_id": r.conversation_id,
                "question": r.question or "",
                "answer": r.answer or "",
            }
            for r in rows
        ],
    }
