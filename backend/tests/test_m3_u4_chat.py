"""M3-U4：/chat 端点，含隔离、落库、空间无文档。"""

import json
import uuid

import pytest

from app.engine.base import EngineResult
from app.models.document import Document
from app.services import answer_service

pytestmark = pytest.mark.asyncio


class _FakeEngine:
    """返回 Agent 式 JSON（answer + doc_numbers）。"""

    def __init__(self, answer="基于文档的回答", doc_numbers=None):
        self._payload = json.dumps(
            {"answer": answer, "doc_numbers": doc_numbers or []}
        )

    async def complete(self, prompt, *, files=None, system=None):
        return EngineResult(text=self._payload)


async def _ws(client, headers, name="ws"):
    r = await client.post("/workspaces", json={"name": name}, headers=headers)
    return r.json()["id"]


async def _make_ready_doc(db_session, ws_id, *, title, content):
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(ws_id),
        title=title,
        storage_key=f"{ws_id}/{uuid.uuid4().hex}",
        mime_type="text/plain",
        summary=content,
        tags=["t"],
        content_text=content,
        status="ready",
    )
    db_session.add(doc)
    await db_session.commit()
    return doc


async def test_chat_empty_workspace_no_docs(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    resp = await client.post(
        "/chat",
        json={"workspace_id": ws_id, "message": "任意问题"},
        headers=admin,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == answer_service.NO_DOCS_ANSWER
    assert body["sources"] == []
    assert "conversation_id" in body


async def test_chat_with_hit_returns_answer_and_sources(
    client, seed_user, db_session, monkeypatch
):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    await _make_ready_doc(db_session, ws_id, title="防火墙", content="firewall policy")
    # Claude 选中第 1 篇文档
    monkeypatch.setattr(
        answer_service, "get_engine", lambda *a, **k: _FakeEngine(doc_numbers=[1])
    )

    resp = await client.post(
        "/chat", json={"workspace_id": ws_id, "message": "firewall"}, headers=admin
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "基于文档的回答"
    assert len(body["sources"]) == 1
    assert body["sources"][0]["title"] == "防火墙"


async def test_chat_non_member_403(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    _, partner = await seed_user("partner")
    resp = await client.post(
        "/chat", json={"workspace_id": ws_id, "message": "hi"}, headers=partner
    )
    assert resp.status_code == 403


async def test_chat_persists_messages(client, seed_user, monkeypatch):
    # 第二轮有历史 → 无命中也会调引擎，用 stub 避免真实 CLI
    monkeypatch.setattr(answer_service, "get_engine", lambda *a, **k: _FakeEngine())
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    first = await client.post(
        "/chat", json={"workspace_id": ws_id, "message": "问题一"}, headers=admin
    )
    conv_id = first.json()["conversation_id"]
    # 复用同一会话
    await client.post(
        "/chat",
        json={"workspace_id": ws_id, "message": "问题二", "conversation_id": conv_id},
        headers=admin,
    )
    hist = await client.get(f"/conversations/{conv_id}", headers=admin)
    assert hist.status_code == 200
    # 两轮：每轮 user + assistant = 4 条
    assert len(hist.json()["messages"]) == 4


async def test_chat_requires_auth(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    resp = await client.post("/chat", json={"workspace_id": ws_id, "message": "hi"})
    assert resp.status_code == 401
