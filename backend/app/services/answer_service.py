"""Agent 式问答 service：把整个空间的知识索引交给 Claude，由它智能理解、
组织答案，并挑出相关文档作为可下载来源。

原则：
- 不做关键词硬匹配；喂结构化索引（标题/分类/标签/摘要）让 Claude 智能判断。
- LLM 只经 app/engine/（唯一出口）。
- 文档来源由 Claude 按“索引编号”选择，服务端据编号映射回真实文档，防止 ID 幻觉。
- 索引数量设上限保护；超限截断并记录，不静默（SECURITY 原则）。
"""

import json
import logging
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.engine.base import get_engine
from app.models.document import Category, Document
from app.storage.base import get_storage

logger = logging.getLogger(__name__)

NO_DOCS_ANSWER = "当前空间还没有已归类的文档，暂时无法回答。"

# 单次喂给 Claude 的索引条目上限（控制 token）；超出则按最近优先截断并 log。
MAX_INDEX_DOCS = 200

_ANSWER_PROMPT = """你是企业知识库的智能问答助手。下面是本知识库中所有文档的索引\
（编号、标题、分类、标签、摘要）。请理解用户的问题，基于这些索引智能作答：
- 综合相关文档给出有帮助的回答，可使用 Markdown 格式。
- 挑出与问题最相关的文档编号（可为空），供用户下载原文。
- 若索引中确无相关内容，如实说明，不要编造。
{history}
用户问题：{question}

文档索引：
{catalog}

请只输出一个 JSON 对象，格式：
{{"answer": "给用户看的 Markdown 回答", "doc_numbers": [相关文档的编号数组]}}
不要输出 JSON 以外的内容。"""


@dataclass
class AnswerResult:
    answer: str
    sources: list[dict] = field(default_factory=list)


async def _build_source(doc: Document) -> dict:
    storage = get_storage()
    ttl = get_settings().download_url_ttl_sec
    return {
        "doc_id": str(doc.id),
        "title": doc.title,
        "download_url": await storage.download_url(doc.storage_key, ttl),
    }


def _format_history(history: list[tuple[str, str]] | None) -> str:
    if not history:
        return ""
    lines = ["\n对话历史（供理解上下文）："]
    for role, content in history:
        who = "用户" if role == "user" else "助手"
        lines.append(f"{who}：{content}")
    lines.append("")
    return "\n".join(lines)


async def _load_index(
    session: AsyncSession, workspace_id: uuid.UUID
) -> list[tuple[Document, str | None]]:
    """加载空间内所有 ready 文档及其分类名（最近优先，带上限保护）。"""
    stmt = (
        select(Document, Category.name)
        .outerjoin(Category, Category.id == Document.category_id)
        .where(Document.workspace_id == workspace_id, Document.status == "ready")
        .order_by(Document.created_at.desc())
        .limit(MAX_INDEX_DOCS + 1)
    )
    rows = (await session.execute(stmt)).all()
    if len(rows) > MAX_INDEX_DOCS:
        logger.warning(
            "workspace %s 文档数超过索引上限 %d，本次问答按最近优先截断",
            workspace_id,
            MAX_INDEX_DOCS,
        )
        rows = rows[:MAX_INDEX_DOCS]
    return [(doc, cat) for doc, cat in rows]


def _build_catalog(index: list[tuple[Document, str | None]]) -> str:
    lines = []
    for n, (doc, cat) in enumerate(index, start=1):
        tags = "、".join(doc.tags or []) or "无"
        summary = (doc.summary or "").replace("\n", " ")
        lines.append(
            f"[{n}] 标题：{doc.title} | 分类：{cat or '未分类'} | "
            f"标签：{tags}\n    摘要：{summary}"
        )
    return "\n".join(lines)


def _parse_engine_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("引擎输出中未找到 JSON 对象")
    return json.loads(text[start : end + 1])


async def answer_question(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    question: str,
    category_id: uuid.UUID | None = None,
    history: list[tuple[str, str]] | None = None,
) -> AnswerResult:
    """喂全空间知识索引 → Claude 智能作答 + 选相关文档 → 返回 answer + sources。"""
    index = await _load_index(session, workspace_id)

    # 空间无任何已归类文档且无历史上下文：无从作答。
    if not index and not history:
        return AnswerResult(answer=NO_DOCS_ANSWER, sources=[])

    catalog = _build_catalog(index) if index else "（本空间暂无已归类文档）"

    from app.services.settings_service import get_engine_backend

    engine = get_engine(await get_engine_backend(session))
    result = await engine.complete(
        _ANSWER_PROMPT.format(
            question=question, catalog=catalog, history=_format_history(history)
        )
    )

    # 解析 Claude 输出：answer + 选中的文档编号
    try:
        parsed = _parse_engine_json(result.text)
        answer = str(parsed.get("answer") or "").strip()
        doc_numbers = parsed.get("doc_numbers") or []
    except (ValueError, json.JSONDecodeError):
        # 兜底：解析失败时把原文当答案，不带来源
        return AnswerResult(answer=result.text.strip(), sources=[])

    # 按编号映射回真实文档（服务端控制，防 ID 幻觉）
    sources = []
    for num in doc_numbers:
        if isinstance(num, int) and 1 <= num <= len(index):
            sources.append(await _build_source(index[num - 1][0]))

    return AnswerResult(answer=answer or result.text.strip(), sources=sources)
