"""Progress reflects real completion order and does not leave retrieval jobs running."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.agents.base import AgentRegistry
from app.core.config import get_settings
from app.services import answer_service
from tests.test_chat_agents import FakeAgent, FakeEngine, mock_prompts


def setup_agents(monkeypatch, agents):
    monkeypatch.setattr(
        answer_service, "build_registry", AsyncMock(return_value=AgentRegistry(agents)),
    )
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=FakeEngine()))
    mock_prompts(monkeypatch)


@pytest.mark.asyncio
async def test_fast_agent_finishes_while_slow_agent_is_still_running(monkeypatch):
    release = asyncio.Event()

    class SlowAgent(FakeAgent):
        async def retrieve(self, *args):
            await release.wait()
            return await super().retrieve(*args)

    setup_agents(monkeypatch, [
        SlowAgent("slow"), FakeAgent("fast"), FakeAgent("failed", fail=True),
    ])
    monkeypatch.setattr(get_settings(), "chat_retrieval_concurrency", 3)
    stream = answer_service.answer_question_streamed(None, workspace_id=[], question="configure")
    snapshots = []
    try:
        async with asyncio.timeout(3):
            async for event in stream:
                if isinstance(event, answer_service.Stage) and event.agent_runs:
                    snapshots.append(event.agent_runs)
                    runs = {r["agent_id"]: r for r in event.agent_runs}
                    if runs["fast"]["status"] == "done" and runs["failed"]["status"] == "failed":
                        assert runs["slow"]["status"] == "running"
                        assert runs["fast"]["evidence_count"] == 1
                        break
            else:
                pytest.fail("No live completion snapshot received")
        # Previously emitted snapshots must not mutate as later jobs finish.
        assert all(r["status"] == "queued" for r in snapshots[0])
        release.set()
        remaining = [event async for event in stream]
        result = next(e for e in remaining if isinstance(e, answer_service.AnswerResult))
        assert [r["status"] for r in result.agent_runs] == ["done", "done", "failed"]
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_queued_agents_do_not_claim_to_be_running_and_close_cancels_jobs(monkeypatch):
    cancelled = asyncio.Event()

    class BlockingAgent(FakeAgent):
        async def retrieve(self, *args):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    second = FakeAgent("queued")
    setup_agents(monkeypatch, [BlockingAgent("blocked"), second])
    monkeypatch.setattr(get_settings(), "chat_retrieval_concurrency", 1)
    stream = answer_service.answer_question_streamed(None, workspace_id=[], question="configure")
    try:
        async with asyncio.timeout(3):
            async for event in stream:
                if isinstance(event, answer_service.Stage) and event.agent_runs:
                    if event.agent_runs[0]["status"] == "running":
                        assert event.agent_runs[1]["status"] == "queued"
                        break
    finally:
        await stream.aclose()
    assert cancelled.is_set()
    assert not second.called
