"""M3-U8：SSE 流式对话，推送工作阶段 + 最终答案。"""

import json
import uuid

import pytest

from app.engine.base import EngineResult
from app.models.document import Document
from app.services import answer_service

pytestmark = pytest.mark.asyncio


class _FakeEngine:
    def __init__(self, answer="流式答案", doc_numbers=None):
        self._payload = json.dumps({"answer": answer, "doc_numbers": doc_numbers or []})

    async def complete(self, prompt, *, files=None, system=None):
        return EngineResult(text=self._payload)


async def _ws(client, headers):
    return (await client.post("/workspaces", json={"name": "ws"}, headers=headers)).json()["id"]


async def _ready_doc(session, ws_id, title="文档A"):
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(ws_id),
        title=title,
        storage_key=f"{ws_id}/{uuid.uuid4().hex}",
        mime_type="text/plain",
        summary="摘要",
        tags=["t"],
        status="ready",
    )
    session.add(doc)
    await session.commit()
    return doc


def _parse_sse(text: str):
    """把 SSE 文本解析成 [(event, data_dict)]。"""
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event, data = None, None
        for line in block.split("\n"):
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if event:
            events.append((event, data))
    return events


async def test_stream_emits_stages_then_done(client, seed_user, db_session, monkeypatch):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    await _ready_doc(db_session, ws_id)
    monkeypatch.setattr(
        answer_service, "get_engine", lambda *a, **k: _FakeEngine(doc_numbers=[1])
    )

    resp = await client.post(
        "/chat/stream", json={"workspace_id": ws_id, "message": "有什么文档"}, headers=admin
    )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

    events = _parse_sse(resp.text)
    kinds = [e for e, _ in events]
    # 至少有 stage 事件，且以 done 结尾
    assert "stage" in kinds
    assert kinds[-1] == "done"

    done_data = events[-1][1]
    assert done_data["answer"] == "流式答案"
    assert len(done_data["sources"]) == 1
    assert "conversation_id" in done_data

    # 阶段应包含检索/思考等标识
    stage_ids = [d["stage"] for e, d in events if e == "stage"]
    assert "indexing" in stage_ids
    assert "thinking" in stage_ids


async def test_stream_non_member_403(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    _, partner = await seed_user("partner")
    resp = await client.post(
        "/chat/stream", json={"workspace_id": ws_id, "message": "hi"}, headers=partner
    )
    assert resp.status_code == 403
