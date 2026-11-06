"""Context overflow, independent sessions, cancellation and visible citation degradation."""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.agents.base import AgentRegistry, Evidence
from app.agents.citations import has_invalid_citations, strip_citations, validate_citations
from app.agents.workspace import WorkspaceAgent
from app.core.config import get_settings
from app.engine.base import EngineError, EngineResult
from app.models.auth import Workspace
from app.models.document import Document
from app.schemas.chat import MessagePublic
from app.services import answer_service
from app.services.conversation_export_service import build_export
from app.services.workspace_retrieval import ContextBudgetError, bounded_map, select_documents
from tests.test_chat_agents import FakeAgent, FakeEngine, mock_prompts


def test_degradation_strips_citations_but_preserves_code():
    answer = "Step [S1]. Other [S99](https://invalid.test). `[S2]`\n```\n[S3]\n```"
    cleaned = strip_citations(answer)
    assert cleaned == "Step . Other . `[S2]`\n```\n[S3]\n```"
    evidence = [Evidence(id="1", agent_id="a", title="doc", excerpt="content")]
    assert has_invalid_citations(answer, evidence)
    assert validate_citations("[S1](https://invalid.test)", evidence)[0] == "[S1]"


@pytest.mark.asyncio
async def test_overflow_scans_every_document_then_compares_batches_globally(monkeypatch):
    monkeypatch.setattr(get_settings(), "chat_prompt_budget_bytes", 16000)
    monkeypatch.setattr(get_settings(), "chat_retrieval_top_k", 10)
    rows = [
        dict(
            doc_id=str(n),
            workspace_id="a",
            title=f"Doc {n}",
            category=None,
            tags=[],
            summary="metadata " * 35,
        )
        for n in range(1000)
    ]

    class RankedEngine:
        def __init__(self):
            self.pages = []

        async def complete(self, prompt):
            assert len(prompt.encode()) <= 16000
            batch, _ = json.JSONDecoder().raw_decode(prompt)
            self.pages.append(batch)
            ranked = sorted(batch, key=lambda r: int(r["doc_id"]), reverse=True)
            return EngineResult(
                text=json.dumps({"mode": "fetch", "doc_ids": [r["doc_id"] for r in ranked[:10]]})
            )

    engine = RankedEngine()
    result = await select_documents(rows, "configure firewall", [], engine, "{catalog}")
    assert {r["doc_id"] for page in engine.pages for r in page} == {str(i) for i in range(1000)}
    assert [r["doc_id"] for r, _ in result] == [str(i) for i in range(999, 989, -1)]
    assert len(engine.pages[-1]) <= 40
    assert any(
        any(abs(int(a["doc_id"]) - int(b["doc_id"])) > 1
            for a, b in zip(page, page[1:], strict=False))
        for page in engine.pages
    )  # Re-ranking combines finalists from separated original batches.


@pytest.mark.asyncio
async def test_unbounded_single_metadata_is_rejected_before_engine_call(monkeypatch):
    monkeypatch.setattr(get_settings(), "chat_prompt_budget_bytes", 16000)
    engine = AsyncMock()
    with pytest.raises(ContextBudgetError):
        await select_documents(
            [{"doc_id": "1", "summary": "x" * 20000}], "q", [], engine, "{catalog}"
        )
    engine.complete.assert_not_called()


@pytest.mark.asyncio
async def test_parallel_workspace_reads_use_independent_sessions(db_session, monkeypatch):
    spaces = [Workspace(id=uuid.uuid4(), name=f"Space {n}") for n in range(3)]
    db_session.add_all(spaces)
    await db_session.commit()
    active, peak, sessions = 0, 0, set()
    barrier = asyncio.Event()
    original = WorkspaceAgent.load_index

    async def load(agent):
        nonlocal active, peak
        sessions.add(id(agent.session))
        assert agent.session is not db_session
        await agent.session.execute(text("SELECT 1"))
        active += 1
        peak = max(peak, active)
        if active == 3:
            barrier.set()
        try:
            await asyncio.wait_for(barrier.wait(), timeout=2)
            return await original(agent)
        finally:
            active -= 1

    monkeypatch.setattr(WorkspaceAgent, "load_index", load)
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=FakeEngine()))
    result = await answer_service.answer_question(
        db_session,
        workspace_id=[w.id for w in spaces],
        question="configuration",
    )
    assert len(sessions) == 3 and peak == 3
    assert all(r["status"] == "done" for r in result.agent_runs)


@pytest.mark.asyncio
async def test_cancellation_cleans_up_bounded_children(monkeypatch):
    monkeypatch.setattr(get_settings(), "chat_retrieval_concurrency", 2)
    active, cleaned = set(), set()
    ready = asyncio.Event()

    async def worker(n):
        active.add(n)
        if len(active) == 2:
            ready.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.add(n)

    task = asyncio.create_task(bounded_map(range(8), worker))
    await asyncio.wait_for(ready.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(active) == 2 and cleaned == active


@pytest.mark.asyncio
async def test_repair_outage_preserves_answer_with_warning(monkeypatch):
    engine = FakeEngine(answer="Useful draft [S99].")
    engine.complete = AsyncMock(side_effect=EngineError("offline"))
    monkeypatch.setattr(
        answer_service,
        "build_registry",
        AsyncMock(
            return_value=AgentRegistry([FakeAgent("a")]),
        ),
    )
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    mock_prompts(monkeypatch)
    result = await answer_service.answer_question(None, workspace_id=[], question="q")
    assert result.answer == "Useful draft ." and result.sources == []
    assert result.warning == "citation_degraded" and result.error_key is None


@pytest.mark.asyncio
async def test_degradation_survives_api_history_and_export(
    client, seed_user, db_session, monkeypatch
):
    _, headers = await seed_user("admin")
    ws = Workspace(id=uuid.uuid4(), name="test")
    db_session.add(ws)
    await db_session.flush()
    db_session.add(
        Document(
            workspace_id=ws.id,
            title="doc",
            storage_key="doc",
            mime_type="text/plain",
            status="ready",
            content_text="Steps.",
        )
    )
    await db_session.commit()
    engine = FakeEngine(payload={"doc_numbers": [1]}, answer="Steps [S99].")
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    response = await client.post("/chat", json={"message": "configuration"}, headers=headers)
    body = response.json()
    assert body["warning"] == "citation_degraded" and body["sources"] == []
    assert body["answer"] == "Steps ."
    history = (
        await client.get(f"/conversations/{body['conversation_id']}", headers=headers)
    ).json()
    message = history["messages"][-1]
    assert message["retrieval"]["warning"] == "citation_degraded"
    saved = MessagePublic(**message)
    markdown, _, _ = build_export("test", [saved], "md")
    assert "Unverified citations" in markdown.decode()
    assert "[S99]" not in markdown.decode()


@pytest.mark.asyncio
async def test_large_inventory_summaries_preserve_original_citation_ids(monkeypatch):
    from app.services.synthesis_context import fit_synthesis_context

    monkeypatch.setattr(get_settings(), "chat_prompt_budget_bytes", 16000)
    evidence = [Evidence(id=str(n), agent_id="a", title=f"Product {n}", excerpt="data " * 400)
                for n in range(40)]
    entries = [{"citation_id": f"S{n}", "title": e.title, "excerpt": e.excerpt}
               for n, e in enumerate(evidence, 1)]
    calls = []

    class Summarizer:
        async def complete(self, prompt):
            assert len(prompt.encode()) <= 16000
            group, _ = json.JSONDecoder().raw_decode(prompt)
            calls.append(group)
            return EngineResult(text="\n".join(
                f"{e['title']} [{e['citation_id']}]" for e in group
            ))

    prompt = await fit_synthesis_context(
        entries, evidence, lambda rows: json.dumps(rows, ensure_ascii=False), Summarizer(),
    )
    assert len(calls) > 1 and sum(len(group) for group in calls) == 40
    assert len(prompt.encode()) <= 16000
    assert "[S1]" in prompt and "[S40]" in prompt
    assert all(e.title in prompt for e in evidence)


@pytest.mark.asyncio
async def test_summary_cannot_cite_a_different_batch(monkeypatch):
    from app.services.synthesis_context import fit_synthesis_context

    monkeypatch.setattr(get_settings(), "chat_prompt_budget_bytes", 16000)
    evidence = [Evidence(id=str(n), agent_id="a", title=str(n), excerpt="x" * 9000)
                for n in range(2)]
    entries = [{"citation_id": f"S{n}", "excerpt": e.excerpt}
               for n, e in enumerate(evidence, 1)]
    engine = AsyncMock()
    engine.complete.return_value = EngineResult(text="Claim [S2]")
    with pytest.raises(EngineError):
        await fit_synthesis_context(entries, evidence, json.dumps, engine)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['index', 'fetch', 'answer'])
@pytest.mark.parametrize('field', ['fetch_numbers', 'doc_numbers'])
async def test_stored_prompt_number_fields_are_independent_of_retrieval_mode(mode, field):
    rows = [{'doc_id': 'real-document', 'workspace_id': 'authorized', 'title': 'Guide'}]
    engine = AsyncMock()
    # Live engines can obey a stored fetch_numbers schema while choosing index mode.
    engine.complete.return_value = EngineResult(text=json.dumps({
        'mode': mode, field: [True, 1, 1, 999],
    }))
    selected = await select_documents(rows, 'q', [], engine, '{catalog}')
    assert len(selected) == 1 and selected[0][0]['doc_id'] == 'real-document'
    assert selected[0][1] is (mode == 'fetch')
