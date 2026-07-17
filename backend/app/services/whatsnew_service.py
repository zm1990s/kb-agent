"""What's New 业务逻辑：生成空间新动态摘要，查询用户可见报告。"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.engine.base import EngineError, get_chat_engine
from app.models.auth import Workspace
from app.models.document import Category, Document
from app.models.whatsnew import WhatsNewReport
from app.services.settings_service import (
    MODEL_WHATSNEW_KEY,
    TASK_HEADERS_WHATSNEW_KEY,
    WHATSNEW_PROMPT_KEY,
    get_prompt,
    get_task_headers,
)
from app.services.workspace_service import list_my_workspaces
from app.storage.base import get_storage

logger = logging.getLogger(__name__)

WHATSNEW_WINDOW_DAYS = 7


async def generate_for_workspace(
    session: AsyncSession,
    *,
    workspace: Workspace,
    window_days: int = WHATSNEW_WINDOW_DAYS,
) -> WhatsNewReport | None:
    """查最近 window_days 天 ready 文档 → 若无文档则跳过 → 调 LLM → 存报告，返回 None 表示跳过。"""
    now = datetime.now(UTC)
    period_start = now - timedelta(days=window_days)
    # Document.created_at 列无时区（naive），查询参数必须去掉 tzinfo
    period_start_naive = period_start.replace(tzinfo=None)

    stmt = (
        select(Document, Category.name)
        .outerjoin(Category, Category.id == Document.category_id)
        .where(
            Document.workspace_id == workspace.id,
            Document.status == "ready",
            Document.deleted_at.is_(None),
            Document.created_at >= period_start_naive,
        )
        .order_by(Document.created_at.desc())
    )
    rows = (await session.execute(stmt)).all()

    if not rows:
        logger.info("whatsnew workspace=%s no new docs, skip", workspace.id)
        return None

    doc_ids = [doc.id for doc, _ in rows]

    doc_lines = []
    for n, (doc, cat) in enumerate(rows, start=1):
        tags = "、".join(doc.tags or []) or "无"
        summary = (doc.summary or "").replace("\n", " ")
        upload_date = doc.created_at.strftime("%Y-%m-%d")
        doc_lines.append(
            f"[{n}] 标题：{doc.title} | 分类：{cat or '未分类'} | 标签：{tags}\n"
            f"    上传：{upload_date} | 摘要：{summary}"
        )
    documents_text = "\n".join(doc_lines)

    period_str = (
        f"{period_start.strftime('%Y-%m-%d')} 至 {now.strftime('%Y-%m-%d')}"
    )
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S UTC")

    prompt_tpl = await get_prompt(session, WHATSNEW_PROMPT_KEY)
    prompt = prompt_tpl.format(
        workspace_name=workspace.name,
        period=period_str,
        doc_count=len(rows),
        documents=documents_text,
        timestamp=timestamp,
    )

    engine = await get_chat_engine(
        session,
        extra_headers=await get_task_headers(session, TASK_HEADERS_WHATSNEW_KEY),
        model_key=MODEL_WHATSNEW_KEY,
    )
    try:
        result = await engine.complete(prompt)
    except EngineError as exc:
        logger.error("whatsnew engine 调用失败 workspace=%s: %s", workspace.id, exc)
        raise
    summary_md = result.text.strip()

    report = WhatsNewReport(
        workspace_id=workspace.id,
        period_start=period_start,
        period_end=now,
        summary=summary_md,
        doc_ids=doc_ids,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    logger.info(
        "whatsnew generated workspace=%s docs=%d report=%s",
        workspace.id, len(rows), report.id,
    )
    return report


async def _build_report_dicts(
    session: AsyncSession,
    *,
    reports: list[WhatsNewReport],
    ws_map: dict,
) -> list[dict]:
    """将 WhatsNewReport 列表转成前端/邮件用的 dict 列表（含文档下载链接）。"""
    if not reports:
        return []

    all_doc_ids: list[uuid.UUID] = []
    for r in reports:
        all_doc_ids.extend(r.doc_ids)

    docs_by_id: dict[uuid.UUID, tuple[Document, str | None]] = {}
    if all_doc_ids:
        doc_stmt = (
            select(Document, Category.name)
            .outerjoin(Category, Category.id == Document.category_id)
            .where(Document.id.in_(all_doc_ids))
        )
        for doc, cat_name in (await session.execute(doc_stmt)).all():
            docs_by_id[doc.id] = (doc, cat_name)

    storage = get_storage()
    ttl = get_settings().download_url_ttl_sec

    output = []
    for report in reports:
        ws = ws_map.get(report.workspace_id)
        if ws is None:
            continue
        doc_list = []
        for doc_id in report.doc_ids:
            entry = docs_by_id.get(doc_id)
            if entry is None:
                continue
            doc, cat_name = entry
            try:
                url = await storage.download_url(doc.storage_key, ttl)
            except Exception:
                url = ""
            doc_list.append({
                "doc_id": str(doc.id),
                "title": doc.title,
                "category": cat_name or "未分类",
                "tags": doc.tags or [],
                "download_url": url,
            })
        output.append({
            "workspace_id": str(ws.id),
            "workspace_name": ws.name,
            "period_start": report.period_start.isoformat(),
            "period_end": report.period_end.isoformat(),
            "created_at": report.created_at.isoformat(),
            "summary": report.summary,
            "documents": doc_list,
        })
    return output


async def get_latest_reports_for_user(
    session: AsyncSession,
    *,
    user,
) -> list[dict]:
    """返回当前用户可见空间的最新一条报告（用于页面展示）。"""
    my_workspaces = await list_my_workspaces(session, user=user)
    if not my_workspaces:
        return []

    ws_map = {ws.id: ws for ws, _ in my_workspaces}
    ws_ids = list(ws_map.keys())

    from sqlalchemy import func
    subq = (
        select(
            WhatsNewReport.workspace_id,
            func.max(WhatsNewReport.created_at).label("max_created_at"),
        )
        .where(WhatsNewReport.workspace_id.in_(ws_ids))
        .group_by(WhatsNewReport.workspace_id)
        .subquery()
    )
    stmt = (
        select(WhatsNewReport)
        .join(
            subq,
            (WhatsNewReport.workspace_id == subq.c.workspace_id)
            & (WhatsNewReport.created_at == subq.c.max_created_at),
        )
        .order_by(WhatsNewReport.workspace_id)
    )
    reports = list((await session.execute(stmt)).scalars().all())
    return await _build_report_dicts(session, reports=reports, ws_map=ws_map)


async def get_reports_for_user_since(
    session: AsyncSession,
    *,
    user,
    since: datetime | None,
) -> list[dict]:
    """返回 since 时间点之后（用于邮件聚合）该用户可见空间的所有报告，按空间+时间排序。

    since=None 表示从未发送过，返回每个空间最新一条（避免首次发送堆积历史数据）。
    """
    my_workspaces = await list_my_workspaces(session, user=user)
    if not my_workspaces:
        return []

    ws_map = {ws.id: ws for ws, _ in my_workspaces}
    ws_ids = list(ws_map.keys())

    if since is None:
        # 首次：每个 workspace 取最新一条，同 get_latest_reports_for_user
        from sqlalchemy import func
        subq = (
            select(
                WhatsNewReport.workspace_id,
                func.max(WhatsNewReport.created_at).label("max_created_at"),
            )
            .where(WhatsNewReport.workspace_id.in_(ws_ids))
            .group_by(WhatsNewReport.workspace_id)
            .subquery()
        )
        stmt = (
            select(WhatsNewReport)
            .join(
                subq,
                (WhatsNewReport.workspace_id == subq.c.workspace_id)
                & (WhatsNewReport.created_at == subq.c.max_created_at),
            )
            .order_by(WhatsNewReport.workspace_id)
        )
    else:
        # since 之后的所有报告，按空间、时间排序
        stmt = (
            select(WhatsNewReport)
            .where(
                WhatsNewReport.workspace_id.in_(ws_ids),
                WhatsNewReport.created_at > since,
            )
            .order_by(WhatsNewReport.workspace_id, WhatsNewReport.created_at)
        )

    reports = list((await session.execute(stmt)).scalars().all())
    return await _build_report_dicts(session, reports=reports, ws_map=ws_map)
