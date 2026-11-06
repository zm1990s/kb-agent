"""Full workspace indexes and scoped evidence fetching; no namespace routing."""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, String, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentDescriptor, Evidence, RetrievalResult
from app.engine.base import EngineProtocol
from app.models.auth import Workspace
from app.models.document import Category, Document

MAX_EXCERPT_CHARS = 6000


def document_uploaded_at():
    """Normalize migration timestamptz and legacy naive UTC ORM timestamps."""
    return cast(case(
        (cast(func.pg_typeof(Document.created_at), String) == "timestamp without time zone",
         func.timezone("UTC", cast(Document.created_at, DateTime(timezone=False)))),
        else_=Document.created_at,
    ), DateTime(timezone=True))


def select_excerpt(text: str, query: str) -> tuple[str, str]:
    """Select a bounded passage, including matches beyond the document prefix.

    Offsets refer to processed content_text, not pages of the original file.
    """
    terms = set(re.findall(r"[a-zA-Z0-9_.-]{2,}|[\u4e00-\u9fff]{2,}", query.lower()))
    # Chinese bigrams also work with unsegmented text and mixed-language queries.
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", query):
        terms.update(phrase[i:i + 2] for i in range(len(phrase) - 1))
    stride = MAX_EXCERPT_CHARS // 2
    starts = range(0, max(1, len(text)), stride)
    start = max(starts, key=lambda pos: sum(
        min(text[pos:pos + MAX_EXCERPT_CHARS].lower().count(term), 3) for term in terms
    ))
    excerpt = text[start:start + MAX_EXCERPT_CHARS]
    return excerpt, f"content_text:{start}-{start + len(excerpt)}"


class WorkspaceAgent:
    def __init__(self, session: AsyncSession, workspace: Workspace, category_id=None):
        self.session = session
        self.workspace = workspace
        # Legacy category_id never restricts the full workspace index.
        self.descriptor = AgentDescriptor(
            id=f"workspace:{workspace.id}", name=workspace.name,
            description=(workspace.description or "")[:2000], workspace_id=str(workspace.id),
        )

    async def load_index(self) -> list[dict]:
        uploaded_at = document_uploaded_at()
        rows = (await self.session.execute(select(
            Document.id, Document.title, Document.summary, Document.tags,
            uploaded_at.label("uploaded_at"), Category.name.label("category"),
        ).outerjoin(Category, (Category.id == Document.category_id) & (
            Category.workspace_id == self.workspace.id
        )).where(
            Document.workspace_id == self.workspace.id,
            Document.status == "ready", Document.deleted_at.is_(None),
        ).order_by(uploaded_at.desc(), Document.id.desc()))).all()
        return [
            {"doc_id": str(row.id), "workspace_id": str(self.workspace.id),
             "title": row.title, "category": row.category, "tags": row.tags,
             "summary": row.summary or "",
             "uploaded_at": row.uploaded_at.astimezone(UTC).isoformat()}
            for row in rows
        ]

    async def fetch_selected(
        self, selections: list[tuple[dict, bool]], question: str,
    ) -> list[Evidence]:
        evidence = []
        for fetch_body in (False, True):
            selected = [row for row, fetch in selections if fetch == fetch_body]
            if not selected:
                continue
            columns = [Document.id, Document.title, Document.summary]
            if fetch_body:
                columns.append(Document.content_text)
            docs = (await self.session.execute(select(*columns).where(
                Document.id.in_([uuid.UUID(row["doc_id"]) for row in selected]),
                Document.workspace_id == self.workspace.id,
                Document.status == "ready", Document.deleted_at.is_(None),
            ))).all()
            by_id = {str(doc.id): doc for doc in docs}
            for row in selected:
                doc = by_id.get(row["doc_id"])
                if doc is None:
                    continue
                metadata = json.dumps(row, ensure_ascii=False)
                content = (doc.content_text or doc.summary or "") if fetch_body else ""
                kind, locator = "document_metadata", "document index metadata"
                excerpt = "文档索引信息：\n" + metadata
                if content.strip():
                    passage, locator = select_excerpt(content, question)
                    kind = "processed_text" if doc.content_text else "summary"
                    if kind == "summary":
                        locator = locator.replace("content_text:", "summary:")
                    excerpt += "\n\n正文片段：\n" + passage
                    locator = "document index metadata; " + locator
                digest = hashlib.sha256(excerpt.encode()).hexdigest()[:16]
                evidence.append(Evidence(
                    id=f"document:{doc.id}:{digest}", title=doc.title, excerpt=excerpt,
                    agent_id=self.descriptor.id, doc_id=str(doc.id),
                    workspace_id=str(self.workspace.id), workspace_name=self.workspace.name,
                    locator=locator, content_kind=kind, uploaded_at=row["uploaded_at"],
                    retrieved_at=datetime.now(UTC).isoformat(),
                ))
        return evidence

    async def retrieve(
        self, question: str, history: list[tuple[str, str]], engine: EngineProtocol,
    ) -> RetrievalResult:
        from app.services.settings_service import ANSWER_FETCH_PROMPT_KEY, get_prompt
        from app.services.workspace_retrieval import select_documents

        rows = await self.load_index()
        template = await get_prompt(self.session, ANSWER_FETCH_PROMPT_KEY)
        selected = await select_documents(rows, question, history, engine, template)
        return RetrievalResult(
            evidence=await self.fetch_selected(selected, question), indexed_count=len(rows),
        )
