"""No-hit answers use model knowledge, preserve history and never invent KB citations."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.base import AgentRegistry
from app.engine.base import EngineResult, TextChunk
from app.schemas.chat import MessagePublic
from app.services import answer_service
from app.services.conversation_export_service import build_export
from tests.test_chat_agents import FakeAgent, FakeEngine, mock_prompts


@pytest.mark.asyncio
async def test_no_authorized_spaces_can_answer_from_knowledge_without_citations(monkeypatch):
    engine = SimpleNamespace(complete=AsyncMock(return_value=EngineResult(
        text="General advice [S99]. Example: `[S1]`.",
    )))
    monkeypatch.setattr(answer_service, "build_registry", AsyncMock(return_value=AgentRegistry([])))
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    mock_prompts(monkeypatch)
    result = await answer_service.answer_question(
        None,
        workspace_id=[],
        question="Explain DNS",
        history=[("user", "I use Linux")],
    )
    assert result.error_key is None and result.warning == "knowledge_fallback"
    assert result.answer == "General advice . Example: `[S1]`." and result.sources == []
    engine.complete.assert_awaited_once()
    prompt = engine.complete.call_args.args[0]
    assert "Explain DNS" in prompt and "I use Linux" in prompt
    assert "已有通用知识" in prompt and "不能编造知识库实际存有的文档" in prompt


@pytest.mark.asyncio
async def test_retrieval_failure_is_not_presented_as_a_clean_no_hit(monkeypatch):
    engine = FakeEngine()
    monkeypatch.setattr(
        answer_service,
        "build_registry",
        AsyncMock(
            return_value=AgentRegistry([FakeAgent("a", fail=True)]),
        ),
    )
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    mock_prompts(monkeypatch)
    result = await answer_service.answer_question(None, workspace_id=[], question="Explain DNS")
    assert result.error_key == "retrieval_failed" and result.warning is None
    assert not engine.prompts


@pytest.mark.asyncio
async def test_fallback_stream_history_and_export(client, seed_user, monkeypatch):
    _, headers = await seed_user("admin")
    ws = (await client.post("/workspaces", json={"name": "Empty"}, headers=headers)).json()
    prompts = []

    class KnowledgeEngine:
        async def complete(self, prompt):
            raise AssertionError("Empty index needs no selection or citation-repair call")

        async def complete_streaming(self, prompt):
            prompts.append(prompt)
            yield TextChunk("DNS maps domain names to IP addresses.")

    monkeypatch.setattr(
        answer_service, "get_chat_engine", AsyncMock(return_value=KnowledgeEngine())
    )
    response = await client.post(
        "/chat/stream",
        json={
            "workspace_id": ws["id"],
            "message": "Explain DNS",
        },
        headers=headers,
    )
    events = []
    for block in response.text.split("\n\n"):
        lines = block.splitlines()
        if len(lines) >= 2 and lines[0].startswith("event: ") and lines[1].startswith("data: "):
            events.append((lines[0][7:], json.loads(lines[1][6:])))
    result = next(data for kind, data in events if kind == "done")
    assert result["answer"] == "DNS maps domain names to IP addresses."
    assert result["sources"] == [] and result["warning"] == "knowledge_fallback"
    assert not result.get("error_key")
    assert any(
        data.get("message_key") == "stage_general_knowledge"
        for kind, data in events
        if kind == "stage"
    )
    history = (
        await client.get(f"/conversations/{result['conversation_id']}", headers=headers)
    ).json()
    saved = MessagePublic(**history["messages"][-1])
    assert saved.retrieval["warning"] == "knowledge_fallback"
    exported, _, _ = build_export("DNS", [saved], "md")
    assert "未引用知识库文档" in exported.decode() and "[S1]" not in exported.decode()
    followup = await client.post(
        "/chat",
        json={
            "workspace_id": ws["id"],
            "conversation_id": result["conversation_id"],
            "message": "Explain how caching helps",
        },
        headers=headers,
    )
    assert followup.json()["warning"] == "knowledge_fallback"
    assert "Explain DNS" in prompts[-1] and result["answer"] in prompts[-1]
