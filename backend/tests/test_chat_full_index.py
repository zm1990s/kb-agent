"""Automatic Chat scans complete authorized indexes before synthesizing cited answers."""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, text

from app.agents import workspace as workspace_module
from app.engine.base import EngineResult, TextChunk
from app.models.auth import Workspace, WorkspaceMember
from app.models.document import Document
from app.models.rbac import Group, GroupMember, GroupPermission
from app.services import answer_service, settings_service


class FullIndexEngine:
    def __init__(self, mode="index"):
        self.pages = []
        self.synthesis = []
        self.mode = mode

    async def complete(self, prompt, **kwargs):
        rows, _ = json.JSONDecoder().raw_decode(prompt)
        assert rows and "citation_id" not in rows[0]
        assert "你是知识检索路由器" not in prompt and "product_catalog" not in prompt
        self.pages.append(rows)
        return EngineResult(text=json.dumps({
            "mode": self.mode, "doc_numbers": [r["number"] for r in rows],
            "fetch_numbers": [r["number"] for r in rows],
        }))

    async def complete_streaming(self, prompt, **kwargs):
        sources, _ = json.JSONDecoder().raw_decode(prompt)
        self.synthesis.append(sources)
        yield TextChunk("综合回答：\n" + "\n".join(
            f'- {s["title"]} [{s["citation_id"]}]' for s in sources
        ))


def patch_engine(monkeypatch, engine):
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    monkeypatch.setattr(workspace_module, "get_prompt", AsyncMock(return_value="{catalog}"))
    monkeypatch.setattr(settings_service, "get_prompt", AsyncMock(return_value="{catalog}"))
    monkeypatch.setattr(settings_service, "get_task_headers", AsyncMock(return_value={}))


def document(ws, title, **kwargs):
    return Document(
        id=uuid.uuid4(), workspace_id=ws.id, title=title, storage_key=uuid.uuid4().hex,
        mime_type="text/plain", status=kwargs.pop("status", "ready"),
        created_at=datetime(2020, 1, 1), summary="PAN-OS and Prisma Access index summary",
        content_text="BODY_SECRET_GlobalProtect", tags=["PAN-OS"], **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("timezone_column", [False, True])
@pytest.mark.parametrize("question", [
    "PAN-OS 怎么配置？", "知识库里有哪些产品的文档？", "获取所有最近文档更新",
])
async def test_full_index_has_no_space_product_or_document_count_filter(
    client, seed_user, db_session, db_engine, monkeypatch, timezone_column, question,
):
    uid, headers = await seed_user("user")
    spaces = [Workspace(id=uuid.uuid4(), name=f"Unrelated finance {i}") for i in range(5)]
    private = Workspace(id=uuid.uuid4(), name="Private")
    group = Group(id=uuid.uuid4(), name="Chat users")
    db_session.add_all([*spaces, private, group])
    await db_session.flush()
    db_session.add_all([
        GroupMember(group_id=group.id, user_id=uid),
        GroupPermission(group_id=group.id, module="chat", level="read"),
        *[WorkspaceMember(workspace_id=ws.id, user_id=uid, role_in_ws="viewer") for ws in spaces],
    ])
    expected = []
    for i, ws in enumerate(spaces):
        docs = [document(ws, f"Guide {i}-{j}") for j in range(225 if i == 0 else 2)]
        expected.extend(str(doc.id) for doc in docs)
        db_session.add_all(docs)
    db_session.add_all([
        document(private, "PRIVATE_DOCUMENT"),
        document(spaces[0], "DELETED_DOCUMENT", deleted_at=datetime.now(UTC)),
        document(spaces[0], "PROCESSING_DOCUMENT", status="processing"),
    ])
    await db_session.commit()
    if timezone_column:
        await db_session.execute(text(
            "ALTER TABLE documents ALTER COLUMN created_at TYPE timestamptz "
            "USING created_at AT TIME ZONE 'UTC'"
        ))
        await db_session.commit()
    engine = FullIndexEngine()
    patch_engine(monkeypatch, engine)
    queries = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", capture)
    try:
        response = await client.post("/chat", json={
            "message": question, "agent_ids": [f"workspace:{spaces[4].id}"],
            "category_id": str(uuid.uuid4()),
        }, headers=headers)
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    body = response.json()
    assert body["error_key"] is None
    assert len(body["agent_runs"]) == 5
    assert sum(r["indexed_count"] for r in body["agent_runs"]) == 233
    assert all(r["status"] == "done" and not r["truncated"] for r in body["agent_runs"])
    assert {s["doc_id"] for s in body["sources"]} == set(expected)
    assert len(engine.pages) == 10  # 6 pages in the large space, one in each other space.
    assert sum(len(page) for page in engine.pages) == 233
    assert all(len(page) <= 40 for page in engine.pages)
    assert len(engine.synthesis) == 1 and len(engine.synthesis[0]) == 233
    assert all(s["content_kind"] == "document_metadata" for s in body["sources"])
    assert all(datetime.fromisoformat(s["uploaded_at"]) == datetime(2020, 1, 1, tzinfo=UTC)
               for s in body["sources"])
    serialized = json.dumps(engine.pages)
    for secret in ["PRIVATE_DOCUMENT", "DELETED_DOCUMENT", "PROCESSING_DOCUMENT", "BODY_SECRET"]:
        assert secret not in serialized
    assert not any("documents.content_text" in q for q in queries)
    history = (await client.get(
        f'/conversations/{body["conversation_id"]}', headers=headers,
    )).json()
    saved = next(m for m in reversed(history["messages"]) if m["role"] == "assistant")
    assert saved["sources"] == body["sources"]
    assert saved["retrieval"]["agent_runs"] == body["agent_runs"]
    explicit = await client.post("/chat", json={
        "message": question, "workspace_id": str(spaces[4].id),
    }, headers=headers)
    assert explicit.status_code == 200
    assert len(explicit.json()["sources"]) == 2
    assert {s["workspace_id"] for s in explicit.json()["sources"]} == {str(spaces[4].id)}


@pytest.mark.asyncio
async def test_stream_runs_index_retrieval_then_synthesis(
    client, seed_user, db_session, monkeypatch,
):
    _, headers = await seed_user("admin")
    spaces = [Workspace(id=uuid.uuid4(), name=f"Unrelated {i}") for i in range(4)]
    db_session.add_all(spaces)
    await db_session.flush()
    db_session.add_all([document(ws, "PAN-OS") for ws in spaces])
    await db_session.commit()
    engine = FullIndexEngine(mode="fetch")
    patch_engine(monkeypatch, engine)
    response = await client.post("/chat/stream", json={
        "message": "知识库里有哪些产品的文档？",
    }, headers=headers)
    assert response.status_code == 200
    events = []
    for block in response.text.strip().split("\n\n"):
        kind = next((s[7:] for s in block.splitlines() if s.startswith("event: ")), None)
        data = next((s[6:] for s in block.splitlines() if s.startswith("data: ")), None)
        if kind and data:
            events.append((kind, json.loads(data)))
    assert events[-1][0] == "done"
    body = events[-1][1]
    assert not body.get("error_key") and len(body["agent_runs"]) == 4
    assert len(engine.pages) == 4 and len(engine.synthesis) == 1
    assert all(s["content_kind"] == "processed_text" for s in body["sources"])
    assert all("BODY_SECRET" in s["excerpt"] for s in body["sources"])
    assert "".join(d["text"] for k, d in events if k == "token") == body["answer"]
    assert all(d["stage"] != "routing" for k, d in events if k == "stage")
    assert any(d.get("message_key") == "stage_full_index" for k, d in events if k == "stage")
