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
from datetime import UTC, datetime

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
    import re
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("引擎输出中未找到 JSON 对象")
    raw = text[start : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # 转义字符串字面量内的裸控制字符
    def _escape_ctrl(m: re.Match) -> str:
        inner = m.group(0)[1:-1].replace("\\", "\x00BS\x00")
        inner = re.sub(r'[\x00-\x1f]', lambda c: (
            {"\\": "\\\\", "\n": "\\n", "\r": "\\r", "\t": "\\t"}.get(c.group(), f"\\u{ord(c.group()):04x}")
        ), inner)
        return f'"{inner.replace(chr(0) + "BS" + chr(0), "\\")}"'
    return json.loads(re.sub(r'"(?:[^"\\]|\\.)*"', _escape_ctrl, raw, flags=re.DOTALL))


@dataclass
class Stage:
    """流式工作阶段事件（供前端展示 Agent 进展）。"""

    stage: str  # 阶段标识：indexing / thinking / parsing / done
    message: str


async def answer_question_streamed(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    question: str,
    category_id: uuid.UUID | None = None,
    history: list[tuple[str, str]] | None = None,
):
    """生成器：先 yield 若干 Stage 事件，最后 yield 一个 AnswerResult。

    供 SSE 端点消费；answer_question() 是它的收敛封装。
    """
    logger.info("answer start workspace=%s question_len=%d", workspace_id, len(question))
    yield Stage("indexing", "正在检索知识库索引…")
    index = await _load_index(session, workspace_id)

    if not index and not history:
        yield Stage("done", "空间暂无文档")
        yield AnswerResult(answer=NO_DOCS_ANSWER, sources=[])
        return

    if index:
        yield Stage("indexing", f"已载入 {len(index)} 篇文档索引")
    catalog = _build_catalog(index) if index else "（本空间暂无已归类文档）"

    from app.services.settings_service import (
        ANSWER_FETCH_PROMPT_KEY,
        ANSWER_PROMPT_KEY,
        get_engine_backend,
        get_prompt,
    )

    yield Stage("thinking", "Agent 正在阅读索引并判断是否需要原文…")
    engine = get_engine(await get_engine_backend(session))
    hist_text = _format_history(history)
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    # ── Phase 1：只给摘要，让 Agent 判断够不够用 ────────────────
    fetch_prompt_tpl = await get_prompt(session, ANSWER_FETCH_PROMPT_KEY)
    phase1_result = await engine.complete(
        fetch_prompt_tpl.format(
            question=question, catalog=catalog, history=hist_text, timestamp=timestamp
        )
    )

    yield Stage("parsing", "正在解析 Agent 判断结果…")
    try:
        phase1 = _parse_engine_json(phase1_result.text)
    except (ValueError, json.JSONDecodeError):
        yield Stage("done", "完成")
        yield AnswerResult(answer=phase1_result.text.strip(), sources=[])
        return

    if phase1.get("mode") == "fetch":
        # ── Phase 2：拉取原文，再调一次 LLM ───────────────────────
        fetch_numbers: list[int] = [
            n for n in (phase1.get("fetch_numbers") or [])
            if isinstance(n, int) and 1 <= n <= len(index)
        ]
        if fetch_numbers:
            yield Stage("thinking", f"正在获取 {len(fetch_numbers)} 篇文档原文…")
            fulltext_lines = []
            for num in fetch_numbers:
                doc, _ = index[num - 1]
                if doc.content_text:
                    fulltext_lines.append(
                        f"\n[{num}] {doc.title} 原文：\n{doc.content_text[:8000]}"
                    )
            fulltext_block = (
                "\n已获取原文：\n" + "\n".join(fulltext_lines)
                if fulltext_lines else ""
            )
        else:
            fulltext_block = ""

        yield Stage("thinking", "Agent 正在结合原文组织回答…")
        answer_prompt_tpl = await get_prompt(session, ANSWER_PROMPT_KEY)
        result = await engine.complete(
            answer_prompt_tpl.format(
                question=question,
                catalog=catalog,
                history=hist_text,
                fulltext=fulltext_block,
                timestamp=timestamp,
            )
        )
        yield Stage("parsing", "正在整理答案与相关文档…")
        try:
            parsed = _parse_engine_json(result.text)
            answer = str(parsed.get("answer") or "").strip()
            doc_numbers = parsed.get("doc_numbers") or []
        except (ValueError, json.JSONDecodeError):
            yield Stage("done", "完成")
            yield AnswerResult(answer=result.text.strip(), sources=[])
            return
    else:
        # mode == "answer"：摘要已够，直接用 Phase 1 的结果
        answer = str(phase1.get("answer") or "").strip()
        doc_numbers = phase1.get("doc_numbers") or []

    sources = []
    for num in doc_numbers:
        if isinstance(num, int) and 1 <= num <= len(index):
            sources.append(await _build_source(index[num - 1][0]))

    logger.info("answer done workspace=%s sources=%d", workspace_id, len(sources))
    yield Stage("done", "完成")
    yield AnswerResult(answer=answer or phase1_result.text.strip(), sources=sources)


async def answer_question(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    question: str,
    category_id: uuid.UUID | None = None,
    history: list[tuple[str, str]] | None = None,
) -> AnswerResult:
    """非流式封装：消费流式生成器，返回最终 AnswerResult。"""
    result = AnswerResult(answer=NO_DOCS_ANSWER, sources=[])
    async for item in answer_question_streamed(
        session,
        workspace_id=workspace_id,
        question=question,
        category_id=category_id,
        history=history,
    ):
        if isinstance(item, AnswerResult):
            result = item
    return result
