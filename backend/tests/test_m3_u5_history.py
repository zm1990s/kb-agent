"""M3-U5：会话历史，重点隔离（他人会话不可见）与多轮顺序。"""

import uuid

import pytest

from app.engine.base import EngineResult, TextChunk
from app.services import answer_service

pytestmark = pytest.mark.asyncio


class _StubEngine:
    async def complete(self, prompt, *, files=None, system=None):
        return EngineResult(text="{}")

    async def complete_streaming(self, prompt, *, system=None, files=None):
        yield TextChunk(text="stub 答案")


@pytest.fixture(autouse=True)
def _stub_engine(monkeypatch):
    async def _engine(*a, **k): return _StubEngine()
    monkeypatch.setattr(answer_service, "get_chat_engine", _engine)


async def _ws(client, headers, name="ws"):
    r = await client.post("/workspaces", json={"name": name}, headers=headers)
    return r.json()["id"]


async def _chat(client, headers, ws_id, message, conv_id=None):
    payload = {"workspace_id": ws_id, "message": message}
    if conv_id:
        payload["conversation_id"] = conv_id
    return await client.post("/chat", json=payload, headers=headers)


async def test_history_returns_messages_in_order(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    first = await _chat(client, admin, ws_id, "第一问")
    conv_id = first.json()["conversation_id"]
    await _chat(client, admin, ws_id, "第二问", conv_id)

    hist = await client.get(f"/conversations/{conv_id}", headers=admin)
    msgs = hist.json()["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == "第一问"
    assert msgs[2]["content"] == "第二问"


async def test_other_user_cannot_see_conversation(client, seed_user):
    """隔离核心：他人的会话历史不可见（404，不泄漏存在性）。"""
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    conv_id = (await _chat(client, admin, ws_id, "私密问题")).json()["conversation_id"]

    # 另一个用户（即便也是 admin）访问不属于自己的会话
    _, other = await seed_user("admin")
    resp = await client.get(f"/conversations/{conv_id}", headers=other)
    assert resp.status_code == 404


async def test_unknown_conversation_404(client, seed_user):
    _, admin = await seed_user("admin")
    resp = await client.get(f"/conversations/{uuid.uuid4()}", headers=admin)
    assert resp.status_code == 404


async def test_history_requires_auth(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    conv_id = (await _chat(client, admin, ws_id, "q")).json()["conversation_id"]
    resp = await client.get(f"/conversations/{conv_id}")
    assert resp.status_code == 401
