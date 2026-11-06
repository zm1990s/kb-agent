"""Recent-document overviews must cover the authorized scope without semantic caps."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.agents.base import AgentDescriptor, AgentRegistry, Evidence, RetrievalResult
from app.agents.updates import document_updates_query, format_document_updates
from app.agents.workspace import WorkspaceAgent
from app.engine.base import EngineError
from app.models.auth import Workspace, WorkspaceMember
from app.models.document import Document
from app.models.rbac import Group, GroupMember, GroupPermission
from app.services import answer_service

NOW = datetime(2026, 11, 6, 8, 30, tzinfo=UTC)


@pytest.mark.parametrize("question,days", [
    ("获取所有最近文档更新", 7),
    ("请列出所有空间近期新增的文档", 7),
    ("查看过去 14 天上传的文件", 14),
    ("汇总最近两周的文档更新", 14),
    ("list all recent document updates", 7),
    ("show new documents across all workspaces in the past 2 weeks", 14),
    ("获取最近一个月文档更新", 30),
])
def test_overview_intent_and_default_window(question, days):
    query = document_updates_query(question, now=NOW)
    assert query is not None
    assert query.until == NOW
    assert query.since == NOW - timedelta(days=days)


@pytest.mark.parametrize("question", [
    "最近 PAN-OS 文档更新", "GlobalProtect 的文档有哪些更新？",
    "list recent documents about firewall", "获取最近文档更新并部署配置",
    "你有哪些空间", "过去 0 天更新的文档", "How do I update documents?",
])
def test_topic_or_action_requests_do_not_fan_out(question):
    assert document_updates_query(question, now=NOW) is None


@pytest.mark.parametrize("question,since,until", [
    ("昨天的文档更新", "2026-11-05T00:00:00+08:00", "2026-11-06T00:00:00+08:00"),
    ("今天的文档更新", "2026-11-06T00:00:00+08:00", "2026-11-06T16:30:00+08:00"),
    ("本周文档更新", "2026-11-02T00:00:00+08:00", "2026-11-06T16:30:00+08:00"),
    ("上周文档更新", "2026-10-26T00:00:00+08:00", "2026-11-02T00:00:00+08:00"),
    ("本月文档更新", "2026-11-01T00:00:00+08:00", "2026-11-06T16:30:00+08:00"),
    ("documents updated last month", "2026-10-01T00:00:00+08:00",
     "2026-11-01T00:00:00+08:00"),
])
def test_calendar_windows_use_shanghai(question, since, until):
    query = document_updates_query(question, now=NOW)
    assert query.since == datetime.fromisoformat(since)
    assert query.until == datetime.fromisoformat(until)


@pytest.mark.asyncio
async def test_overview_routes_every_workspace_without_calling_model():
    agents = [SimpleNamespace(descriptor=AgentDescriptor(
        id=str(i), name=str(i), description="unrelated topic",
    )) for i in range(6)]
    external = SimpleNamespace(descriptor=AgentDescriptor(
        id="external", name="docs", description="docs", source_type="docs",
    ))
    engine = SimpleNamespace(complete=AsyncMock(side_effect=AssertionError("no semantic route")))
    assert await AgentRegistry([*agents, external]).route(
        "获取所有最近文档更新", [], engine,
    ) == agents
    engine.complete.assert_not_called()


def _document(ws, title, created_at, **kwargs):
    return Document(
        id=uuid.uuid4(), workspace_id=ws.id, title=title, storage_key=uuid.uuid4().hex,
        mime_type="text/plain", created_at=created_at, status=kwargs.pop("status", "ready"),
        summary="document summary", content_text="BODY MUST NOT BE RETRIEVED", **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("timezone_column", [False, True])
async def test_auto_overview_pages_all_spaces_and_persists_sources(
    client, seed_user, db_session, monkeypatch, stream, timezone_column,
):
    user_id, headers = await seed_user("user")
    group = Group(id=uuid.uuid4(), name="Chat users")
    db_session.add(group)
    await db_session.flush()
    db_session.add_all([
        GroupMember(group_id=group.id, user_id=user_id),
        GroupPermission(group_id=group.id, module="chat", level="read"),
    ])
    spaces = [Workspace(id=uuid.uuid4(), name=f"Space {i}") for i in range(5)]
    private = Workspace(id=uuid.uuid4(), name="Unauthorized")
    db_session.add_all([*spaces, private])
    await db_session.flush()
    db_session.add_all([WorkspaceMember(
        workspace_id=ws.id, user_id=user_id, role_in_ws="viewer",
    ) for ws in spaces])
    recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
    expected = []
    for i, ws in enumerate(spaces):
        # Identical timestamps straddle a page boundary; UUID is the keyset tie-breaker.
        docs = [_document(ws, f"Doc {i}-{j}", recent) for j in range(105 if i == 0 else 2)]
        expected.extend(str(doc.id) for doc in docs)
        db_session.add_all(docs)
    db_session.add_all([
        _document(spaces[0], "Stale", recent - timedelta(days=8)),
        _document(spaces[0], "Processing", recent, status="processing"),
        _document(spaces[0], "Deleted", recent, deleted_at=recent.replace(tzinfo=UTC)),
        _document(private, "Secret", recent),
    ])
    await db_session.commit()
    if timezone_column:
        # Match the real migration schema, not just Base.metadata.create_all().
        await db_session.execute(text(
            "ALTER TABLE documents ALTER COLUMN created_at TYPE timestamptz "
            "USING created_at AT TIME ZONE 'UTC'"
        ))
        await db_session.commit()
    # Exercise a non-UTC database locale too; upload dates still represent UTC instants.
    await db_session.execute(text("SET TIME ZONE 'Asia/Shanghai'"))
    await db_session.commit()
    factory = AsyncMock(side_effect=AssertionError("overview must not require an AI engine"))
    monkeypatch.setattr(answer_service, "get_chat_engine", factory)
    response = await client.post(
        "/chat/stream" if stream else "/chat",
        json={"message": "获取所有最近文档更新"}, headers=headers,
    )
    assert response.status_code == 200
    if stream:
        events = []
        for block in response.text.strip().split("\n\n"):
            kind = next((s[7:] for s in block.splitlines() if s.startswith("event: ")), None)
            data = next((s[6:] for s in block.splitlines() if s.startswith("data: ")), None)
            if kind and data:
                events.append((kind, json.loads(data)))
        assert events[-1][0] == "done"
        body = events[-1][1]
        assert "".join(d["text"] for k, d in events if k == "token") == body["answer"]
    else:
        body = response.json()
    assert body.get("error_key") is None
    assert len(body["agent_runs"]) == 5
    assert all(r["status"] == "done" and not r["truncated"] for r in body["agent_runs"])
    assert {s["doc_id"] for s in body["sources"]} == set(expected)
    assert len(body["sources"]) == 113
    for source in body["sources"]:
        assert f'[{source["citation_id"]}]' in body["answer"]
        assert source["content_kind"] == "document_metadata"
        assert datetime.fromisoformat(source["uploaded_at"]) == recent.replace(tzinfo=UTC)
        assert "BODY MUST NOT" not in source["excerpt"]
    for excluded in ["Stale", "Processing", "Deleted", "Secret"]:
        assert excluded not in body["answer"]
    assert "不代表原文件的修改时间" in body["answer"]
    history = (await client.get(
        f'/conversations/{body["conversation_id"]}', headers=headers,
    )).json()
    saved = history["messages"][-1]
    assert saved["sources"] == body["sources"]
    assert saved["retrieval"]["agent_runs"] == body["agent_runs"]
    factory.assert_not_called()

    filtered = await client.post("/chat", json={
        "message": "获取所有最近文档更新", "agent_ids": [f"workspace:{spaces[4].id}"],
    }, headers=headers)
    assert filtered.status_code == 200
    assert len(filtered.json()["sources"]) == 2
    assert {s["workspace_id"] for s in filtered.json()["sources"]} == {str(spaces[4].id)}


@pytest.mark.asyncio
async def test_empty_overview_does_not_reuse_history_as_updates(db_session, monkeypatch):
    ws = Workspace(id=uuid.uuid4(), name="Empty")
    db_session.add(ws)
    await db_session.commit()
    result = await answer_service.answer_question(
        db_session, workspace_id=ws.id, question="获取所有最近文档更新",
        history=[("assistant", "Yesterday a document was added [S1]")],
    )
    assert result.error_key is None
    assert result.sources == []
    assert "没有找到新增已归类文档" in result.answer


@pytest.mark.asyncio
async def test_update_query_time_boundaries_are_half_open(db_session):
    ws = Workspace(id=uuid.uuid4(), name="Boundaries")
    db_session.add(ws)
    await db_session.flush()
    query = document_updates_query("昨天文档更新", now=NOW)
    since = query.since.astimezone(UTC).replace(tzinfo=None)
    until = query.until.astimezone(UTC).replace(tzinfo=None)
    db_session.add_all([
        _document(ws, "At start", since),
        _document(ws, "Before start", since - timedelta(microseconds=1)),
        _document(ws, "Before end", until - timedelta(microseconds=1)),
        _document(ws, "At end", until),
    ])
    await db_session.commit()
    result = await WorkspaceAgent(db_session, ws).retrieve_updates(query)
    assert [item.title for item in result.evidence] == ["Before end", "At start"]


@pytest.mark.asyncio
async def test_failed_workspace_is_reported_without_discarding_other_sources(
    db_session, monkeypatch,
):
    spaces = [Workspace(id=uuid.uuid4(), name=name) for name in ["Available", "Failed"]]
    db_session.add_all(spaces)
    await db_session.commit()

    async def retrieve(agent, query):
        if agent.workspace.name == "Failed":
            raise EngineError("unavailable")
        return RetrievalResult(evidence=[Evidence(
            id="doc", title="Document", excerpt="uploaded", agent_id=agent.descriptor.id,
            uploaded_at=NOW.isoformat(),
        )])

    monkeypatch.setattr(WorkspaceAgent, "retrieve_updates", retrieve)
    result = await answer_service.answer_question(
        db_session, workspace_id=[s.id for s in spaces], question="获取所有最近文档更新",
    )
    assert len(result.sources) == 1
    assert "不是完整清单" in result.answer and "Failed" in result.answer
    assert {r["status"] for r in result.agent_runs} == {"done", "failed"}


def test_document_titles_cannot_inject_extra_citations_or_markdown():
    query = document_updates_query("recent document updates", now=NOW)
    evidence = [Evidence(
        id="1", agent_id="a", title="Title [S99] <script>", excerpt="metadata",
        uploaded_at=NOW.isoformat(),
    )]
    answer = format_document_updates(
        query, evidence, [{"agent_id": "a", "name": "A", "status": "done"}],
    )
    assert r"\[S99\]" in answer
    assert r"\<script\>" in answer
    assert "[S1]" in answer
