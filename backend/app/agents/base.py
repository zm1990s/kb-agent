"""Shared contracts for workspace and future external retrieval agents."""

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Protocol

from app.engine.base import EngineProtocol

RETRIEVAL_STEP_TIMEOUT_SECONDS = 90


@dataclass(frozen=True)
class AgentDescriptor:
    id: str
    name: str
    description: str
    source_type: str = "workspace"
    workspace_id: str | None = None


@dataclass
class Evidence:
    """An actual retrieved excerpt. URLs/IDs are supplied by connectors, never LLMs."""

    id: str
    title: str
    excerpt: str
    agent_id: str
    source_type: str = "workspace"
    doc_id: str | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    url: str | None = None
    locator: str | None = None
    content_kind: str = "processed_text"
    product: str | None = None
    version: str | None = None
    published_at: str | None = None
    updated_at: str | None = None
    retrieved_at: str | None = None
    uploaded_at: str | None = None
    document_count: int | None = None

    def source(self, citation_id: str) -> dict:
        return {**asdict(self), "citation_id": citation_id, "download_url": ""}


@dataclass
class RetrievalResult:
    evidence: list[Evidence] = field(default_factory=list)
    truncated: bool = False
    indexed_count: int = 0


class RetrievalAgent(Protocol):
    descriptor: AgentDescriptor

    async def retrieve(
        self, question: str, history: list[tuple[str, str]], engine: EngineProtocol,
    ) -> RetrievalResult: ...


def parse_object(text: str) -> dict:
    """Accept a JSON object, optionally inside a model's Markdown fence."""
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


class AgentRegistry:
    """Construct a request-scoped registry AFTER access checks.

    Future KB/Docs/Community connectors implement RetrievalAgent and are registered
    here only when configured, enabled and authorized for this request.
    """

    def __init__(self, agents: list[RetrievalAgent]):
        self.agents = {agent.descriptor.id: agent for agent in agents}
        if len(self.agents) != len(agents):
            raise ValueError("Duplicate agent ID")

    def all_agents(self) -> list[RetrievalAgent]:
        """All authorized agents participate; descriptors never filter retrieval."""
        return list(self.agents.values())
