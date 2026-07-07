"""M3-U2：全文检索 service，含 workspace 隔离与状态过滤。"""

import uuid

import pytest
from sqlalchemy import func, update

from app.models.auth import Workspace
from app.models.document import Document
from app.services.search_service import search_documents

pytestmark = pytest.mark.asyncio


async def _make_ws(session, name="ws"):
    ws = Workspace(id=uuid.uuid4(), name=name)
    session.add(ws)
    await session.commit()
    return ws


async def _add_doc(session, ws_id, *, title, content, status="ready"):
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        title=title,
        storage_key=f"{ws_id}/{uuid.uuid4().hex}",
        mime_type="text/plain",
        content_text=content,
        summary=content[:50],
        status=status,
    )
    session.add(doc)
    await session.commit()
    # 维护 search_tsv（正常由归类 worker 完成）
    await session.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(
            search_tsv=func.to_tsvector(
                "simple", func.concat_ws(" ", title, content)
            )
        )
    )
    await session.commit()
    return doc


async def test_search_hits_relevant_document(db_session):
    ws = await _make_ws(db_session)
    await _add_doc(db_session, ws.id, title="防火墙配置指南", content="firewall policy setup")
    await _add_doc(db_session, ws.id, title="报销流程", content="expense reimbursement")

    hits = await search_documents(db_session, workspace_id=ws.id, query="firewall")
    assert len(hits) == 1
    assert hits[0].title == "防火墙配置指南"


async def test_search_isolated_by_workspace(db_session):
    ws_a = await _make_ws(db_session, "A")
    ws_b = await _make_ws(db_session, "B")
    await _add_doc(db_session, ws_a.id, title="secret", content="firewall in A")

    # 在 B 空间检索同样的词，命中为空（隔离）
    hits = await search_documents(db_session, workspace_id=ws_b.id, query="firewall")
    assert hits == []


async def test_search_excludes_non_ready(db_session):
    ws = await _make_ws(db_session)
    await _add_doc(
        db_session, ws.id, title="processing doc", content="firewall", status="processing"
    )
    hits = await search_documents(db_session, workspace_id=ws.id, query="firewall")
    assert hits == []


async def test_empty_query_returns_empty(db_session):
    ws = await _make_ws(db_session)
    await _add_doc(db_session, ws.id, title="x", content="firewall")
    assert await search_documents(db_session, workspace_id=ws.id, query="   ") == []


async def test_no_match_returns_empty(db_session):
    ws = await _make_ws(db_session)
    await _add_doc(db_session, ws.id, title="报销", content="expense")
    hits = await search_documents(db_session, workspace_id=ws.id, query="quantum")
    assert hits == []
