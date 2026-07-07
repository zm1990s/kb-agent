"""答案生成 service：把命中文档的原文交给 engine 生成答案，附来源链接。

原则：
- 无命中时明确返回“未找到”，禁止编造（降低幻觉，原文优先）。
- LLM 只经 app/engine/（唯一出口）。
- sources 每项含 doc_id + title + download_url（限时下载端点）。
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.engine.base import get_engine
from app.models.document import Document
from app.services.search_service import search_documents
from app.storage.base import get_storage

NO_MATCH_ANSWER = "未找到相关文档。"

_ANSWER_PROMPT = """你是知识库问答助手。请**仅依据**下面提供的文档原文回答用户问题。
若文档中没有相关信息，直接回答“未找到相关文档。”，不要编造。

用户问题：{question}

可参考的文档原文：
{context}

请用中文简洁作答。"""


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


async def answer_question(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    question: str,
    category_id: uuid.UUID | None = None,
) -> AnswerResult:
    """检索 → 取原文交 engine 生成答案 → 返回 answer + sources。"""
    hits = await search_documents(
        session, workspace_id=workspace_id, query=question, category_id=category_id
    )
    if not hits:
        return AnswerResult(answer=NO_MATCH_ANSWER, sources=[])

    # 拼接命中文档原文作为上下文（原文优先，降低幻觉）
    context_parts = []
    for i, doc in enumerate(hits, start=1):
        body = doc.content_text or doc.summary or ""
        context_parts.append(f"[文档{i}] 标题：{doc.title}\n{body}")
    context = "\n\n".join(context_parts)

    from app.services.settings_service import get_engine_backend

    engine = get_engine(await get_engine_backend(session))
    result = await engine.complete(
        _ANSWER_PROMPT.format(question=question, context=context)
    )

    sources = [await _build_source(doc) for doc in hits]
    return AnswerResult(answer=result.text.strip(), sources=sources)
