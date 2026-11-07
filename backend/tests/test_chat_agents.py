"""Routing isolation, evidence attribution and failure behavior of Chat agents."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.base import AgentDescriptor, AgentRegistry, Evidence, RetrievalResult
from app.agents.citations import validate_citations
from app.agents.workspace import MAX_EXCERPT_CHARS, WorkspaceAgent, select_excerpt
from app.engine.base import EngineError, EngineResult, TextChunk
from app.services import answer_service


class FakeEngine:
    def __init__(self, payload=None, answer="配置说明。[S1]"):
        self.payload = payload or {}
        self.answer = answer
        self.prompts = []

    async def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return EngineResult(text=json.dumps(self.payload))

    async def complete_streaming(self, prompt, **kwargs):
        self.prompts.append(prompt)
        yield TextChunk(self.answer)


class FakeAgent:
    def __init__(self, name, *, fail=False):
        self.descriptor = AgentDescriptor(
            id=name, name=name, description=f"Only {name} products", workspace_id=name,
        )
        self.fail = fail
        self.called = False

    async def retrieve(self, question, history, engine):
        self.called = True
        if self.fail:
            raise EngineError("source unavailable")
        return RetrievalResult(evidence=[Evidence(
            id=self.descriptor.id, title=self.descriptor.name, excerpt="配置说明",
            agent_id=self.descriptor.id, workspace_id=self.descriptor.workspace_id,
        )])


def mock_prompts(monkeypatch):
    from app.services import settings_service
    monkeypatch.setattr(settings_service, "get_prompt", AsyncMock(return_value="{catalog}"))
    monkeypatch.setattr(settings_service, "get_task_headers", AsyncMock(return_value={}))


def test_registry_returns_every_authorized_agent_without_name_filtering():
    agents = [FakeAgent("unrelated " + str(i)) for i in range(8)]
    assert AgentRegistry(agents).all_agents() == agents
    assert AgentRegistry([]).all_agents() == []
    assert not any(agent.called for agent in agents)


def test_excerpt_finds_relevant_content_after_old_prefix_limit():
    text = "intro " * 2500 + "PAN-OS GlobalProtect 配置步骤" + " details" * 20
    excerpt, locator = select_excerpt(text, "PAN-OS GlobalProtect 配置")
    assert "PAN-OS GlobalProtect" in excerpt
    assert len(excerpt) <= MAX_EXCERPT_CHARS
    start, end = map(int, locator.split(":")[1].split("-"))
    assert text[start:end] == excerpt
    assert start > 8000


def test_citations_only_include_actually_used_evidence():
    evidence = [Evidence(id=str(i), title=str(i), excerpt="text", agent_id="a") for i in range(3)]
    answer, sources = validate_citations("结论[S2]；无效[S99]。重复[S2]。", evidence)
    assert "[S99]" not in answer
    assert [s["id"] for s in sources] == ["1"]
    assert sources[0]["citation_id"] == "S2"


def test_code_examples_are_not_citations():
    evidence = [Evidence(id="1", title="doc", excerpt="text", agent_id="a")]
    text = "`[S1]`\n```\n[S1]\n```\n~~~\n[S1]\n~~~"
    assert validate_citations(text, evidence) == (text, [])


@pytest.mark.asyncio
async def test_all_authorized_agents_execute_and_synthesis_sees_evidence(monkeypatch):
    agents = [FakeAgent("firewall"), FakeAgent("finance")]
    engine = FakeEngine({"agent_ids": ["firewall"]})
    monkeypatch.setattr(
        answer_service, "build_registry", AsyncMock(return_value=AgentRegistry(agents)),
    )
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    mock_prompts(monkeypatch)
    result = await answer_service.answer_question(None, workspace_id=[], question="PAN-OS")
    assert agents[0].called and agents[1].called
    assert result.sources[0]["agent_id"] == "firewall"
    assert "finance" in engine.prompts[-1]
    assert result.agent_runs[0]["status"] == "done"


@pytest.mark.asyncio
async def test_one_failed_agent_does_not_discard_other_results(monkeypatch):
    agents = [FakeAgent("a", fail=True), FakeAgent("b")]
    engine = FakeEngine({"agent_ids": ["a", "b"]})
    monkeypatch.setattr(
        answer_service, "build_registry", AsyncMock(return_value=AgentRegistry(agents)),
    )
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    mock_prompts(monkeypatch)
    result = await answer_service.answer_question(None, workspace_id=[], question="compare")
    assert result.sources[0]["agent_id"] == "b"
    assert [run["status"] for run in result.agent_runs] == ["failed", "done"]


@pytest.mark.asyncio
async def test_missing_citations_degrade_after_one_repair(monkeypatch):
    engine = FakeEngine(answer="unsupported answer")
    monkeypatch.setattr(answer_service, "build_registry", AsyncMock(
        return_value=AgentRegistry([FakeAgent("a")]),
    ))
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    mock_prompts(monkeypatch)
    result = await answer_service.answer_question(None, workspace_id=[], question="q")
    assert result.error_key is None and result.warning == "citation_degraded"
    assert result.sources == [] and result.answer == "unsupported answer"
    assert len(engine.prompts) == 2


@pytest.mark.asyncio
async def test_api_rejects_inaccessible_agent_ids(monkeypatch):
    from fastapi import HTTPException

    from app.api import chat
    from app.schemas.chat import ChatRequest
    ws_id = uuid.uuid4()
    monkeypatch.setattr(chat, "list_my_workspaces", AsyncMock(return_value=[(
        SimpleNamespace(id=ws_id), "viewer",
    )]))
    user = SimpleNamespace(id=uuid.uuid4())
    with pytest.raises(HTTPException) as error:
        await chat._resolve_chat_scope(None, user, ChatRequest(message="q", agent_ids=["private"]))
    assert error.value.status_code == 403
    assert await chat._resolve_chat_scope(
        None, user, ChatRequest(message="q", agent_ids=[]),
    ) == [ws_id]
    assert await chat._resolve_chat_scope(None, user, ChatRequest(message="q")) == [ws_id]


@pytest.mark.asyncio
async def test_reconnect_replays_current_agent_stage():
    from app.services import chat_generation as generation
    state = generation.GenerationState(uuid.uuid4(), uuid.uuid4(), False)
    generation._registry[state.conversation_id] = state
    try:
        stage = {"stage": "indexing", "message_key": "stage_agent_searching",
                 "message_params": {"name": "a"}}
        generation._broadcast(state, "stage", stage)
        subscription = generation.subscribe(state.conversation_id, state.user_id)
        assert subscription is not None
        assert subscription[2] == [("stage", stage)]
        generation.unsubscribe(state, subscription[1])
    finally:
        generation._registry.pop(state.conversation_id)


@pytest.mark.asyncio
async def test_workspace_body_query_is_scoped(db_session):
    from app.models.auth import Workspace
    from app.models.document import Document
    ws = Workspace(id=uuid.uuid4(), name="firewall")
    private = Workspace(id=uuid.uuid4(), name="private")
    db_session.add_all([ws, private])
    await db_session.flush()
    for workspace, title in [(ws, "public"), (private, "secret")]:
        db_session.add(Document(
            id=uuid.uuid4(), workspace_id=workspace.id, title=title,
            storage_key=title, mime_type="text/plain", status="ready",
            summary=title, content_text=title,
        ))
    await db_session.commit()
    engine = FakeEngine({"mode": "fetch", "fetch_numbers": [True, 1, 1, 999]})
    result = await WorkspaceAgent(db_session, ws).retrieve("q", [], engine)
    assert len(result.evidence) == 1
    assert result.evidence[0].title == "public"
    assert "secret" not in engine.prompts[0]
    assert result.evidence[0].workspace_id == str(ws.id)


@pytest.mark.asyncio
async def test_auto_full_index_persists_actual_scope_and_citations(
    client, seed_user, db_session, monkeypatch,
):
    from app.models.chat import Conversation
    from app.models.document import Document

    _, headers = await seed_user("admin")
    spaces = []
    for name in ["Firewall", "Finance"]:
        response = await client.post("/workspaces", json={"name": name}, headers=headers)
        spaces.append(uuid.UUID(response.json()["id"]))
    for ws_id, title in zip(spaces, ["PAN-OS", "Private expense details"], strict=True):
        db_session.add(Document(
            id=uuid.uuid4(), workspace_id=ws_id, title=title, storage_key=title,
            mime_type="text/plain", status="ready", summary=title, content_text=title,
        ))
    await db_session.commit()

    class RoutedEngine(FakeEngine):
        async def complete(self, prompt, **kwargs):
            self.prompts.append(prompt)
            if "你是知识检索路由器" in prompt:
                return EngineResult(text=json.dumps({"agent_ids": [f"workspace:{spaces[0]}"]}))
            return EngineResult(text='{"fetch_numbers": [1, 2], "mode": "fetch"}')

    engine = RoutedEngine(answer="配置说明。[S1][S2]")
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    response = await client.post("/chat", json={"message": "PAN-OS"}, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["error_key"] is None
    assert {s["workspace_id"] for s in body["sources"]} == {str(ws) for ws in spaces}
    assert any("Private expense details" in prompt for prompt in engine.prompts)
    assert all("你是知识检索路由器" not in prompt for prompt in engine.prompts)
    conv = await db_session.get(Conversation, uuid.UUID(body["conversation_id"]))
    assert conv.workspace_id is None
    history = (await client.get(f"/conversations/{conv.id}", headers=headers)).json()
    saved = history["messages"][-1]
    assert saved["sources"] == body["sources"]
    assert saved["retrieval"]["agent_runs"] == body["agent_runs"]
    assert len(saved["retrieval"]["agent_runs"]) == 2


@pytest.mark.asyncio
async def test_older_relevant_doc_is_found_after_scanning_complete_index(db_session):
    from datetime import datetime

    from sqlalchemy import func

    from app.models.auth import Workspace
    from app.models.document import Document
    ws = Workspace(id=uuid.uuid4(), name="PAN-OS")
    db_session.add(ws)
    await db_session.flush()
    for i in range(205):
        db_session.add(Document(
            id=uuid.uuid4(), workspace_id=ws.id, title=f"Recent unrelated {i}",
            storage_key=str(i), mime_type="text/plain", status="ready",
            summary="unrelated", content_text="unrelated",
            created_at=datetime(2026, 1, 1), search_tsv=func.to_tsvector("simple", "unrelated"),
        ))
    old_id = uuid.uuid4()
    db_session.add(Document(
        id=old_id, workspace_id=ws.id, title="GlobalProtect", storage_key="old",
        mime_type="text/plain", status="ready", summary="GlobalProtect", content_text="config",
        created_at=datetime(2020, 1, 1), search_tsv=func.to_tsvector("simple", "GlobalProtect"),
    ))
    await db_session.commit()
    class CompleteIndexEngine(FakeEngine):
        async def complete(self, prompt, **kwargs):
            catalog = json.loads(prompt.split("文档目录：\n")[1].split("\n只输出 JSON")[0])
            return EngineResult(text=json.dumps({"doc_numbers": [
                doc["number"] for doc in catalog if "GlobalProtect" in doc["title"]
            ]}))

    result = await WorkspaceAgent(db_session, ws).retrieve(
        "GlobalProtect", [], CompleteIndexEngine(),
    )
    assert not result.truncated and result.indexed_count == 206
    assert result.evidence[0].doc_id == str(old_id)


@pytest.mark.asyncio
async def test_registry_rechecks_revoked_access(db_session, seed_user):
    from app.models.auth import Workspace
    user_id, _ = await seed_user("user")
    ws = Workspace(id=uuid.uuid4(), name="not authorized")
    db_session.add(ws)
    await db_session.commit()
    registry = await answer_service.build_registry(db_session, [ws.id], user_id=user_id)
    assert registry.agents == {}


def test_export_omits_citation_ids_and_keeps_external_links():
    from app.services.conversation_export_service import _source_description
    assert _source_description({"title": "Legacy doc"}) == "Legacy doc"
    text = _source_description({"title": "Setup", "citation_id": "S2", "source_type": "docs",
                                "url": "https://example.com/docs", "version": "11.1"})
    assert "[S2]" not in text and "11.1" in text and "https://example.com/docs" in text


@pytest.mark.asyncio
async def test_retrieval_migration_is_idempotent_and_preserves_old_messages(db_session, seed_user):
    from pathlib import Path

    from sqlalchemy import text

    from app.services.chat_service import add_message, create_conversation
    user_id, _ = await seed_user("user")
    conv = await create_conversation(db_session, workspace_id=None, user_id=user_id)
    message = await add_message(
        db_session, conversation_id=conv.id, role="assistant", content="old answer",
        sources=[{"doc_id": "old-doc", "title": "Legacy source", "download_url": ""}],
    )
    await db_session.execute(text("ALTER TABLE messages DROP COLUMN retrieval"))
    migration = (Path(__file__).parents[2] / "infra/postgres/migrations/044_message_retrieval.sql")
    for _ in range(2):
        await db_session.execute(text(migration.read_text()))
    row = (await db_session.execute(text(
        "SELECT content, sources, retrieval FROM messages WHERE id=:id"
    ), {"id": message.id})).one()
    assert row.content == "old answer"
    assert row.sources[0]["doc_id"] == "old-doc"
    assert row.retrieval == {}
