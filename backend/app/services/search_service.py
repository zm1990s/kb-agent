"""检索 service：PG 全文检索（search_tsv）+ workspace 过滤。

原则（SECURITY #4）：命中集合强制限定当前 workspace，跨空间零泄漏。
不引入向量库；用 plainto_tsquery 安全处理用户输入（防 SQL 注入，SECURITY #7）。
"""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document


async def search_documents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    query: str,
    category_id: uuid.UUID | None = None,
    limit: int = 5,
) -> list[Document]:
    """在空间内按全文检索命中已 ready 的文档，按相关度排序。

    - 强制 workspace 过滤；只检索 status='ready' 的文档。
    - 用 plainto_tsquery（参数化）处理用户输入，避免 tsquery 语法注入。
    - query 为空时返回空列表（交由上层决定“未找到”语义）。
    """
    query = (query or "").strip()
    if not query:
        return []

    tsquery = func.plainto_tsquery("simple", query)
    rank = func.ts_rank(Document.search_tsv, tsquery)

    stmt = (
        select(Document)
        .where(
            Document.workspace_id == workspace_id,
            Document.status == "ready",
            Document.deleted_at.is_(None),
            Document.search_tsv.op("@@")(tsquery),
        )
        .order_by(rank.desc(), Document.created_at.desc())
        .limit(limit)
    )
    if category_id is not None:
        stmt = stmt.where(Document.category_id == category_id)

    result = await session.execute(stmt)
    return list(result.scalars().all())
