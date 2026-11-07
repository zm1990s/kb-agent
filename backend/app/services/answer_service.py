"""Retrieve complete authorized workspace indexes, then synthesize cited answers."""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentRegistry, Evidence, RetrievalAgent, RetrievalResult
from app.agents.citations import has_invalid_citations, strip_citations, validate_citations
from app.agents.paloalto import external_agents
from app.agents.workspace import WorkspaceAgent
from app.core.config import get_settings
from app.engine.base import EngineError, get_chat_engine
from app.models.auth import User, Workspace
from app.services.synthesis_context import fit_synthesis_context
from app.services.temporal_query_service import (
    document_updates_query,
    retrieve_document_updates,
)
from app.services.workspace_retrieval import (
    ContextBudgetError,
    bounded_map,
    retrieve_workspaces,
)

logger = logging.getLogger(__name__)
NO_DOCS_ANSWER = "当前空间还没有已归类的文档，暂时无法回答。"
AGENT_TIMEOUT_SECONDS = 90


@dataclass
class AnswerResult:
    answer: str
    sources: list[dict] = field(default_factory=list)
    error_key: str | None = None
    agent_runs: list[dict] = field(default_factory=list)
    warning: str | None = None


def _format_history(history: list[tuple[str, str]] | None) -> str:
    if not history:
        return ""
    lines = ["\n对话历史（供理解上下文）："]
    for role, content in history:
        who = "用户" if role == "user" else "助手"
        lines.append(f"{who}：{content}")
    return "\n".join([*lines, ""])


@dataclass
class Stage:
    stage: str
    message_key: str
    message_params: dict = field(default_factory=dict)


@dataclass
class TokenChunk:
    text: str


@dataclass
class ThinkingChunk:
    text: str


async def build_registry(
    session: AsyncSession, workspace_id: uuid.UUID | list[uuid.UUID] | None,
    *, user_id: uuid.UUID | None = None, category_id: uuid.UUID | None = None,
    retrieval_sources: list[str] | None = None,
) -> AgentRegistry:
    """Only create agents for authorized workspaces; recheck in detached jobs.

    API callers always supply user_id. Internal service callers can supply an
    already-authorized scope (also used by isolated service tests).
    """
    sources = ["workspace"] if retrieval_sources is None else retrieval_sources
    ws_ids = workspace_id if isinstance(workspace_id, list) else [workspace_id]
    ids = {ws_id for ws_id in ws_ids if ws_id is not None}
    if user_id is not None:
        from app.services.workspace_service import list_my_workspaces

        user = await session.get(User, user_id)
        if user is None:
            return AgentRegistry([])
        allowed = {ws.id for ws, _ in await list_my_workspaces(session, user=user)}
        ids &= allowed
    else:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            "build_registry called without user_id; skipping detached permission re-check. "
            "Ensure caller has already authorized the workspace scope."
        )
    if "workspace" not in sources:
        ids = set()
    workspaces = (await session.execute(
        select(Workspace).where(Workspace.id.in_(ids)).order_by(Workspace.id)
    )).scalars().all() if ids else []
    return AgentRegistry([
        *[WorkspaceAgent(session, ws, category_id) for ws in workspaces],
        *external_agents(sources),
    ])


async def answer_question_streamed(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | list[uuid.UUID] | None,
    question: str,
    category_id: uuid.UUID | None = None,
    history: list[tuple[str, str]] | None = None,
    user_email: str | None = None,
    user_id: uuid.UUID | None = None,
    retrieval_sources: list[str] | None = None,
):
    from app.engine.base import TextChunk as EngineTextChunk
    from app.engine.base import ThinkingChunk as EngineThinkingChunk
    from app.services.settings_service import (
        ANSWER_PROMPT_KEY,
        FALLBACK_PROMPT_KEY,
        TASK_HEADERS_CHAT_KEY,
        get_prompt,
        get_task_headers,
        render_task_headers,
    )

    history = history or []
    yield Stage("indexing", "stage_full_index" if retrieval_sources is None
                or "workspace" in retrieval_sources else "preparing")
    registry = await build_registry(
        session, workspace_id, user_id=user_id, category_id=category_id,
        retrieval_sources=retrieval_sources,
    )
    agents = registry.all_agents()
    temporal = document_updates_query(question)
    if temporal is not None and (
        retrieval_sources is None or set(retrieval_sources) == {"workspace"}
    ):
        yield Stage("indexing", "stage_upload_history")
        answer, sources, runs = await retrieve_document_updates(
            session, temporal, [a for a in agents if isinstance(a, WorkspaceAgent)],
        )
        yield Stage("done", "stage_done")
        yield AnswerResult(answer=answer, sources=sources, agent_runs=runs)
        return
    engine = await get_chat_engine(session, extra_headers=render_task_headers(
        await get_task_headers(session, TASK_HEADERS_CHAT_KEY), user_email=user_email,
    ))
    evidence: list[Evidence] = []
    runs: list[dict] = []
    seen: set[str] = set()
    local = [a for a in agents if isinstance(a, WorkspaceAgent)]
    jobs: list[tuple[str, list[WorkspaceAgent] | RetrievalAgent]] = (
        [("workspaces", local)] if local else []
    )
    jobs.extend(("external", agent) for agent in agents if not isinstance(agent, WorkspaceAgent))
    for agent in agents:
        yield Stage("indexing", "stage_agent_searching", {"name": agent.descriptor.name})

    async def retrieve_job(job):
        kind, target = job
        if kind == "workspaces":
            if temporal is not None:
                _, sources, local_runs = await retrieve_document_updates(session, temporal, target)
                evidence_fields = {f.name for f in fields(Evidence)}
                items = [Evidence(**{k: v for k, v in source.items() if k in evidence_fields})
                         for source in sources]
                counts = {r["agent_id"]: r["document_count"] for r in local_runs}
                return [(a, RetrievalResult(
                    evidence=[e for e in items if e.agent_id == a.descriptor.id],
                    indexed_count=counts.get(a.descriptor.id, 0),
                )) for a in target]
            results = await retrieve_workspaces(target, session, question, history, engine)
            return list(zip(target, results, strict=True))
        try:
            async with asyncio.timeout(AGENT_TIMEOUT_SECONDS):
                result = await target.retrieve(question, history, engine)
            return [(target, result)]
        except (EngineError, TimeoutError, ValueError) as exc:
            logger.exception("External retrieval agent failed agent=%s", target.descriptor.id)
            return [(target, exc)]

    completed = await bounded_map(jobs, retrieve_job)
    results = {agent.descriptor.id: result for group in completed for agent, result in group}
    budget_failed = False
    for agent in agents:
        descriptor = agent.descriptor
        result = results[descriptor.id]
        run = {"agent_id": descriptor.id, "name": descriptor.name,
               "workspace_id": descriptor.workspace_id, "status": "done",
               "source_type": descriptor.source_type}
        runs.append(run)
        if isinstance(result, Exception):
            budget_failed |= isinstance(result, ContextBudgetError)
            run["status"] = "failed"
            yield Stage("indexing", "stage_agent_failed", {"name": descriptor.name})
            continue
        run.update(evidence_count=len(result.evidence), truncated=result.truncated,
                   indexed_count=result.indexed_count)
        for item in result.evidence:
            if item.id not in seen:
                seen.add(item.id)
                evidence.append(item)
    if not evidence and any(r["status"] == "failed" for r in runs):
        yield AnswerResult(
            answer="", error_key="context_budget_exceeded" if budget_failed else "retrieval_failed",
            agent_runs=runs,
        )
        return
    knowledge_fallback = not evidence
    if knowledge_fallback:
        yield Stage("thinking", "stage_general_knowledge")
        fallback_template = await get_prompt(session, FALLBACK_PROMPT_KEY)
        prompt = fallback_template.format(
            question=question,
            history=_format_history(history),
            timestamp=datetime.now(UTC).isoformat(),
        )
        if len(prompt.encode()) > get_settings().chat_prompt_budget_bytes:
            yield AnswerResult(answer="", error_key="context_budget_exceeded", agent_runs=runs)
            return
    else:
        yield Stage("thinking", "stage_thinking_phase2")
        entries = [
            {"citation_id": f"S{n}", "title": item.title, "excerpt": item.excerpt,
             "workspace_name": item.workspace_name, "content_kind": item.content_kind,
             "source_type": item.source_type,
             "url": item.url, "locator": item.locator,
             **{key: getattr(item, key) for key in (
                 "product", "version", "published_at", "updated_at",
                 "indexed_at", "retrieved_at", "uploaded_at",
             ) if getattr(item, key) is not None}}
            for n, item in enumerate(evidence, 1)
        ]
        template = await get_prompt(session, ANSWER_PROMPT_KEY)
        retrieval_status = json.dumps(runs, ensure_ascii=False)
        def build_prompt(candidates):
            return template.format(
                question=question, catalog=json.dumps(candidates, ensure_ascii=False), fulltext="",
                history=_format_history(history), timestamp=datetime.now(UTC).isoformat(),
                retrieval_status=retrieval_status,
            )

        try:
            prompt = await fit_synthesis_context(entries, evidence, build_prompt, engine)
        except ContextBudgetError:
            yield AnswerResult(answer="", error_key="context_budget_exceeded", agent_runs=runs)
            return
        except (EngineError, TimeoutError):
            logger.exception("Evidence compression failed")
            yield AnswerResult(answer="", error_key="engine_unavailable", agent_runs=runs)
            return
    try:
        if hasattr(engine, "complete_streaming"):
            chunks = []
            async for chunk in engine.complete_streaming(prompt):
                if isinstance(chunk, EngineThinkingChunk):
                    yield ThinkingChunk(chunk.text)
                elif isinstance(chunk, EngineTextChunk):
                    chunks.append(chunk.text)
                    yield TokenChunk(chunk.text)
            answer = "".join(chunks).strip()
        else:
            answer = (await engine.complete(prompt)).text.strip()
    except (EngineError, TimeoutError):
        logger.exception("Chat synthesis failed")
        yield AnswerResult(answer="", error_key="engine_unavailable", agent_runs=runs)
        return
    if not answer:
        yield AnswerResult(answer="", error_key="no_answer", agent_runs=runs)
        return
    if knowledge_fallback:
        answer = strip_citations(answer)
        if not answer:
            yield AnswerResult(answer="", error_key="no_answer", agent_runs=runs)
            return
        yield Stage("done", "stage_done")
        yield AnswerResult(answer=answer, sources=[], warning="knowledge_fallback", agent_runs=runs)
        return
    original = answer
    invalid = has_invalid_citations(answer, evidence)
    answer, sources = validate_citations(answer, evidence)
    if not sources or invalid:
        repair_prompt = (
            prompt + "\n上一版缺少有效引用或有无效引用。请重新回答，"
            "仅引用支持结论的证据；不能支持的结论应删除或明确说明不足。"
            "\n上一版：\n" + original
        )
        try:
            if len(repair_prompt.encode()) <= get_settings().chat_prompt_budget_bytes:
                repaired = (await engine.complete(repair_prompt)).text.strip()
                if repaired:
                    invalid = has_invalid_citations(repaired, evidence)
                    answer, sources = validate_citations(repaired, evidence)
        except (EngineError, TimeoutError):
            logger.exception("Citation repair failed; preserving draft with explicit warning")
        if not sources or invalid:
            # No invented sources; prose remains useful but is explicitly unverified.
            yield Stage("done", "stage_done")
            yield AnswerResult(
                answer=strip_citations(original), sources=[], warning="citation_degraded",
                agent_runs=runs,
            )
            return
    yield Stage("parsing", "stage_parsing")
    yield Stage("done", "stage_done")
    yield AnswerResult(answer=answer, sources=sources, agent_runs=runs)


async def answer_question(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID | list[uuid.UUID] | None,
    question: str,
    category_id: uuid.UUID | None = None,
    history: list[tuple[str, str]] | None = None,
    user_email: str | None = None,
    user_id: uuid.UUID | None = None,
    retrieval_sources: list[str] | None = None,
) -> AnswerResult:
    result = AnswerResult(answer=NO_DOCS_ANSWER, error_key="no_docs")
    async for item in answer_question_streamed(
        session, workspace_id=workspace_id, question=question, category_id=category_id,
        history=history, user_email=user_email, user_id=user_id,
        retrieval_sources=retrieval_sources,
    ):
        if isinstance(item, AnswerResult):
            result = item
    return result
