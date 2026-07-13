"""What's New 定时任务：按管理员配置的频率+整点生成摘要，每 1h 派发邮件订阅。"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.models.auth import Workspace

logger = logging.getLogger(__name__)

MAIL_CHECK_INTERVAL_SEC = 3600


def _seconds_until_next_occurrence(target_hour: int, interval_days: int) -> float:
    """返回距下一次执行还有多少秒。

    策略：找到下一个满足 target_hour 整点的时间点，
    且与"现在往前推 interval_days"相比已过间隔。
    实际效果：每 interval_days 天，在 target_hour:00 UTC 触发一次。
    最少返回 60s（避免零点漂移重复触发）。
    """
    now = datetime.now(UTC)
    # 以固定 epoch 为基准，找下一个 interval_days 整倍数天 + target_hour
    epoch = datetime(2024, 1, 1, target_hour, 0, 0, tzinfo=UTC)
    delta_from_epoch = (now - epoch).total_seconds()
    interval_sec = interval_days * 86400
    periods_elapsed = int(delta_from_epoch / interval_sec)
    next_run = epoch + timedelta(seconds=(periods_elapsed + 1) * interval_sec)
    secs = (next_run - now).total_seconds()
    return max(secs, 60.0)


async def run_all_workspaces(window_days: int | None = None) -> None:
    """遍历所有 workspace，逐一生成摘要报告。单个失败不影响其他。

    window_days=None 时从 DB 读取当前配置的生成频率对应天数。
    """
    from app.services.settings_service import WHATSNEW_FREQ_DAYS, get_whatsnew_freq
    from app.services.whatsnew_service import generate_for_workspace

    if window_days is None:
        async with SessionLocal() as session:
            freq = await get_whatsnew_freq(session)
        window_days = WHATSNEW_FREQ_DAYS.get(freq, 7)

    async with SessionLocal() as session:
        result = await session.execute(select(Workspace))
        workspaces = list(result.scalars().all())

    logger.info("whatsnew run start workspaces=%d window_days=%d", len(workspaces), window_days)
    ok = skipped = failed = 0
    for ws in workspaces:
        try:
            async with SessionLocal() as session:
                report = await generate_for_workspace(
                    session, workspace=ws, window_days=window_days
                )
            if report is None:
                skipped += 1
            else:
                ok += 1
        except Exception:
            failed += 1
            logger.exception("whatsnew failed workspace=%s", ws.id)

    logger.info(
        "whatsnew run done ok=%d skipped=%d failed=%d", ok, skipped, failed
    )


async def start_whatsnew_loop() -> None:
    """后台循环：按配置的频率+整点（UTC）执行。配置变更在下次 sleep 前读取。"""
    from app.services.settings_service import (
        WHATSNEW_FREQ_DAYS,
        get_whatsnew_freq,
        get_whatsnew_hour,
    )

    logger.info("whatsnew loop started")
    while True:
        async with SessionLocal() as session:
            target_hour = await get_whatsnew_hour(session)
            freq = await get_whatsnew_freq(session)

        interval_days = WHATSNEW_FREQ_DAYS.get(freq, 7)
        wait = _seconds_until_next_occurrence(target_hour, interval_days)
        next_run = datetime.now(UTC) + timedelta(seconds=wait)
        logger.info(
            "whatsnew loop next run at %s UTC (freq=%s %.0fs from now)",
            next_run.strftime("%Y-%m-%d %H:%M:%S"),
            freq,
            wait,
        )
        await asyncio.sleep(wait)

        try:
            await run_all_workspaces(window_days=interval_days)
        except Exception:
            logger.exception("whatsnew loop unexpected error")


async def run_mail_dispatch() -> None:
    """查到期订阅 → 取 last_sent_at 之后所有报告 → 发邮件 → 更新 last_sent_at。"""
    from app.models.auth import User
    from app.services.email_service import send_whatsnew_digest
    from app.services.whatsnew_service import get_reports_for_user_since
    from app.services.whatsnew_subscription_service import (
        get_due_subscriptions,
        mark_sent,
    )

    async with SessionLocal() as session:
        due = await get_due_subscriptions(session)

    if not due:
        return

    logger.info("whatsnew mail dispatch due=%d", len(due))
    for sub in due:
        try:
            async with SessionLocal() as session:
                # 在新 session 内重新加载，避免 detached 对象无法持久化
                from app.models.whatsnew_subscription import WhatsNewSubscription
                live_sub = await session.get(WhatsNewSubscription, sub.id)
                if live_sub is None:
                    continue
                user = await session.get(User, live_sub.user_id)
                if user is None or not user.is_active:
                    continue
                # 规范化 last_sent_at 时区
                since = None
                if live_sub.last_sent_at is not None:
                    since = (
                        live_sub.last_sent_at.replace(tzinfo=UTC)
                        if live_sub.last_sent_at.tzinfo is None
                        else live_sub.last_sent_at
                    )
                reports = await get_reports_for_user_since(
                    session, user=user, since=since
                )
                if not reports:
                    continue
                await send_whatsnew_digest(user.email, reports)
                await mark_sent(session, sub=live_sub)
        except Exception:
            logger.exception("whatsnew mail dispatch failed sub=%s", sub.id)


async def start_mail_loop() -> None:
    """后台循环：每 1h 检查一次到期邮件订阅。"""
    logger.info("whatsnew mail loop started interval=%ds", MAIL_CHECK_INTERVAL_SEC)
    while True:
        try:
            await run_mail_dispatch()
        except Exception:
            logger.exception("whatsnew mail loop unexpected error")
        await asyncio.sleep(MAIL_CHECK_INTERVAL_SEC)
