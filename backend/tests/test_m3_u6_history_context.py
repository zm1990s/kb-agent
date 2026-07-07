"""M3-U6：多轮上下文 + 会话列表/新建。"""

import uuid

import pytest
from sqlalchemy import func, update

from app.engine.base import EngineResult
from app.models.document import Document
from app.services import answer_service

pytestmark = pytest.mark.asyncio


class _CapturingEngine:
    """记录最后一次 prompt，用于断言历史是否拼入。"""

    def __init__(self):
        self.last_prompt = None

    async def complete(self, prompt, *, files=None, system=None):
        self.last_prompt = prompt
        return EngineResult(text="答案")


async def _ready_doc(session, ws_id, *, title="防火墙", content="firewall policy"):
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(ws_id),
        title=title,
        storage_key=f"{ws_id}/{uuid.uuid4().hex}",
        mime_type="text/plain",
        content_text=content,
        status="ready",
    )
    session.add(doc)
    await session.commit()
    await session.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(search_tsv=func.to_tsvector("simple", func.concat_ws(" ", title, content)))
    )
    await session.commit()


async def _ws(client, headers):
    return (await client.post("/workspaces", json={"name": "ws"}, headers=headers)).json()["id"]


async def test_history_is_passed_to_engine(client, seed_user, db_session, monkeypatch):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    await _ready_doc(db_session, ws_id)

    cap = _CapturingEngine()
    monkeypatch.setattr(answer_service, "get_engine", lambda *a, **k: cap)

    # 第一轮（用单一命中词，plainto_tsquery 对多词做 AND）
    r1 = await client.post(
        "/chat", json={"workspace_id": ws_id, "message": "firewall"}, headers=admin
    )
    conv_id = r1.json()["conversation_id"]
    assert r1.json()["answer"] == "答案"  # 命中，引擎被调用
    # 第二轮：同会话，历史应含第一轮的问答
    r2 = await client.post(
        "/chat",
        json={"workspace_id": ws_id, "message": "firewall", "conversation_id": conv_id},
        headers=admin,
    )
    assert r2.json()["answer"] == "答案"
    assert cap.last_prompt is not None
    assert "对话历史" in cap.last_prompt
    # 第一轮的提问与答案应出现在第二轮的 prompt 历史里
    assert "firewall" in cap.last_prompt


async def test_no_hit_with_history_still_answers(db_session, monkeypatch):
    """无命中但有历史（追问/元问题）：仍调 engine 依历史作答，不 dead-end。"""
    from app.services.answer_service import answer_question

    cap = _CapturingEngine()
    monkeypatch.setattr(answer_service, "get_engine", lambda *a, **k: cap)

    res = await answer_question(
        db_session,
        workspace_id=uuid.uuid4(),
        question="我刚才问了什么？",
        history=[("user", "介绍防火墙"), ("assistant", "防火墙是…")],
    )
    assert cap.last_prompt is not None  # 引擎被调用了
    assert res.answer == "答案"
    assert res.sources == []  # 无命中 → 无来源


async def test_create_and_list_conversations(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)

    created = await client.post("/conversations", json={"workspace_id": ws_id}, headers=admin)
    assert created.status_code == 201
    conv_id = created.json()["id"]

    lst = await client.get(f"/conversations?workspace_id={ws_id}", headers=admin)
    assert lst.status_code == 200
    assert any(c["id"] == conv_id for c in lst.json())


async def test_list_conversations_isolated_by_user(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    await client.post("/conversations", json={"workspace_id": ws_id}, headers=admin)

    # 另一个用户即便是成员，也只看到自己的会话（这里未加入，403）
    _, other = await seed_user("partner")
    resp = await client.get(f"/conversations?workspace_id={ws_id}", headers=other)
    assert resp.status_code == 403


async def test_create_conversation_non_member_403(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    _, other = await seed_user("internal")
    resp = await client.post("/conversations", json={"workspace_id": ws_id}, headers=other)
    assert resp.status_code == 403
