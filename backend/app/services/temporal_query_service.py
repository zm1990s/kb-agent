"""Recognize unqualified document-update overviews separately from topical Q&A."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.agents.base import Evidence
from app.agents.workspace import document_uploaded_at
from app.models.document import Document

_LOCAL_TIME = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class DocumentUpdatesQuery:
    since: datetime
    until: datetime
    language: str
    limit: int | None = 20


def document_updates_query(
    question: str,
    *,
    now: datetime | None = None,
) -> DocumentUpdatesQuery | None:
    """Only match generic overviews; remaining product/topic words prevent fan-out.

    A request to list all recent documents is an explicit scope, not a fallback
    for an unsuccessful semantic route. Unspecified 'recent' means seven days.
    """
    text = question.strip().lower()
    chinese = bool(re.search(r"[\u4e00-\u9fff]", text))
    if chinese:
        if not re.search(r"文档|文件|资料|資料|文檔|檔案|上传|上傳", text):
            return None
        if not re.search(
            r"最近|近期|最新|新增|新上传|更新|今天|昨天|本周|上周|本月|上月|过去", text
        ):
            return None
        remainder = re.sub(r"\d+\s*(?:天|周|星期|个月|月)", "", text)
        remainder = re.sub(
            r"知识库|知識庫|获取|查看|列出|列举|显示|汇总|总结|概览|更新|上传|新增|文档|文件|资料|"
            r"最近|近期|最新|新上传|过去|今天|昨天|本周|上周|本月|上月|一周|两周|一个月|"
            r"哪些|什么|有什么|有哪些|所有|全部|每个|工作空间|工作区|空间|帮我|请|一下|"
            r"的|了|有|新|中|内|和|及|在|从|到|近|里",
            "",
            remainder,
        )
    else:
        if not re.search(r"\b(?:documents?|files?|uploads?|uploaded)\b", text):
            return None
        if not re.search(
            r"\b(?:recent|recently|latest|new|updates?|updated|today|yesterday|"
            r"this week|last week|this month|last month|past \d+|last \d+)\b", text
        ):
            return None
        remainder = re.sub(r"\d+\s*(?:days?|weeks?|months?)", "", text)
        remainder = re.sub(
            r"\b(?:what|which|are|is|were|have|has|been|the|a|an|all|every|any|my|our|"
            r"recent|recently|latest|new|document|documents|file|files|update|updates|updated|"
            r"upload|uploads|uploaded|added|show|list|get|fetch|give|me|please|summary|summarize|"
            r"overview|of|in|across|from|to|and|available|enabled|accessible|workspace|workspaces|"
            r"last|past|this|week|month|today|yesterday)\b",
            "",
            remainder,
        )
    if re.sub(r"[\s，。？！、：；,.?!:;()（）]+", "", remainder):
        return None

    now = (now or datetime.now(UTC)).astimezone(_LOCAL_TIME)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since, until = now - timedelta(days=7), now
    if re.search(r"昨天|\byesterday\b", text):
        since, until = midnight - timedelta(days=1), midnight
    elif re.search(r"今天|\btoday\b", text):
        since = midnight
    elif re.search(r"上周|\blast week\b", text):
        until = midnight - timedelta(days=now.weekday())
        since = until - timedelta(days=7)
    elif re.search(r"本周|\bthis week\b", text):
        since = midnight - timedelta(days=now.weekday())
    elif re.search(r"上月|\blast month\b", text):
        until = midnight.replace(day=1)
        since = (until - timedelta(days=1)).replace(day=1)
    elif re.search(r"本月|\bthis month\b", text):
        since = midnight.replace(day=1)
    else:
        duration = re.search(r"(\d+)\s*(天|周|星期|个月|月|days?|weeks?|months?)", text)
        if duration:
            amount, unit = int(duration[1]), duration[2]
            if amount <= 0:
                return None
            days = amount * (
                7
                if unit in ("周", "星期", "week", "weeks")
                else 30
                if unit in ("个月", "月", "month", "months")
                else 1
            )
            since = now - timedelta(days=min(days, 36500))
        elif "两周" in text:
            since = now - timedelta(days=14)
        elif "一个月" in text:
            since = now - timedelta(days=30)
    unlimited = bool(re.search(r"所有|全部|\ball\b", text))
    return DocumentUpdatesQuery(
        since=since, until=until, language="zh" if chinese else "en",
        limit=None if unlimited else 20,
    )


def _markdown_text(value: str) -> str:
    return re.sub(r"([\\`*_\[\]<>#|])", r"\\\1", " ".join(value.split()))


def format_document_updates(
    query: DocumentUpdatesQuery,
    evidence: list[Evidence],
    runs: list[dict],
    total: int,
) -> str:
    """Render the complete metadata list without a model dropping rows or citations."""
    zh = query.language == "zh"
    period = f"{query.since:%Y-%m-%d %H:%M} — {query.until:%Y-%m-%d %H:%M} (Asia/Shanghai)"
    failed = [run["name"] for run in runs if run["status"] == "failed"]
    if zh:
        lines = [
            f"时间范围：{period}。",
            "",
            "按上传入库时间统计已归类文档；不代表原文件的修改时间。",
            "",
        ]
        lines.append(
            f"本轮检索了 {len(runs)} 个有权限的空间，找到 {total} 篇文档，列出 {len(evidence)} 篇。"
        )
        if failed:
            lines += ["", "部分空间未完成检索，以下结果不是完整清单：" + "、".join(failed) + "。"]
    else:
        lines = [
            f"Time range: {period}.",
            "",
            "Dates are upload times, not original file modification times.",
            "",
        ]
        lines.append(
            f"Searched {len(runs)} accessible workspaces; found {total} documents, "
            f"showing {len(evidence)}."
        )
        if failed:
            lines += [
                "",
                "The list is incomplete; retrieval failed for: " + ", ".join(failed) + ".",
            ]
    if not evidence:
        lines += [
            "",
            "该时间范围内没有找到新增已归类文档。"
            if zh
            else "No newly uploaded, ready documents were found in this time range.",
        ]
    if len(evidence) < total:
        lines += ["", "仅显示最新 20 篇；提问时加上‘所有’可查看完整清单。" if zh
                  else "Showing the latest 20; ask for all documents to see the complete list."]
    for run in runs:
        items = [
            (n, item) for n, item in enumerate(evidence, 1) if item.agent_id == run["agent_id"]
        ]
        if not items:
            continue
        lines += ["", "### " + _markdown_text(run["name"])]
        for n, item in items:
            stamp = (
                datetime.fromisoformat(item.uploaded_at).astimezone(_LOCAL_TIME)
                if item.uploaded_at
                else None
            )
            date = stamp.strftime("%Y-%m-%d %H:%M") if stamp else ""
            lines.append(f"- {_markdown_text(item.title)} · {date} [S{n}]")
    return "\n".join(lines)


async def retrieve_document_updates(session, query, agents):
    """Only authorized scopes reach this query. No model or document body is needed."""
    import uuid

    by_workspace = {agent.descriptor.workspace_id: agent.descriptor for agent in agents}
    uploaded_at = document_uploaded_at()
    predicate = (
        Document.workspace_id.in_([uuid.UUID(ws_id) for ws_id in by_workspace]),
        Document.status == "ready", Document.deleted_at.is_(None),
        uploaded_at >= query.since, uploaded_at < query.until,
    )
    counts = (await session.execute(select(Document.workspace_id, func.count())
                                    .where(*predicate).group_by(Document.workspace_id))).all()
    count_by_workspace = {str(ws_id): count for ws_id, count in counts}
    stmt = select(Document.id, Document.workspace_id, Document.title,
                  uploaded_at.label("uploaded_at")).where(*predicate).order_by(
                      uploaded_at.desc(), Document.id.desc(),
                  )
    if query.limit is not None:
        stmt = stmt.limit(query.limit)
    rows = (await session.execute(stmt)).all()
    evidence = []
    for row in rows:
        descriptor = by_workspace[str(row.workspace_id)]
        stamp = row.uploaded_at.astimezone(UTC).isoformat()
        evidence.append(Evidence(
            id=f"document:{row.id}:uploaded", title=row.title,
            excerpt=f"Title: {row.title}\nUploaded at: {stamp}",
            agent_id=descriptor.id, doc_id=str(row.id), workspace_id=str(row.workspace_id),
            workspace_name=descriptor.name, content_kind="document_metadata",
            locator="documents.created_at (upload time)", uploaded_at=stamp,
        ))
    runs = [
        {"agent_id": d.id, "workspace_id": d.workspace_id, "name": d.name,
         "status": "done", "retrieval_mode": "upload_history",
         "document_count": count_by_workspace.get(ws_id, 0),
         "evidence_count": sum(e.workspace_id == ws_id for e in evidence)}
        for ws_id, d in by_workspace.items()
    ]
    answer = format_document_updates(query, evidence, runs, sum(count_by_workspace.values()))
    return answer, [e.source(f"S{n}") for n, e in enumerate(evidence, 1)], runs
