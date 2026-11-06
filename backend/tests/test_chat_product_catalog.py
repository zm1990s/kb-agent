"""Product inventories use workspace metadata capabilities and keep evidence provenance."""

import json
import uuid
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.base import AgentDescriptor, AgentRegistry
from app.agents.catalog import extract_products, product_catalog_query
from app.engine.base import EngineResult
from app.models.auth import Workspace, WorkspaceMember
from app.models.document import Category, Document
from app.models.rbac import Group, GroupMember, GroupPermission
from app.services import answer_service


@pytest.mark.parametrize("question", [
    "知识库里有哪些产品的文档？", "请列出知识库所有产品的文档", "产品文档覆盖哪些产品？",
    "各个空间有哪些产品资料的文档？", "What products are documented in the knowledge base?",
    "Which products have documents across all workspaces?",
])
def test_generic_product_inventories(question):
    assert product_catalog_query(question)


@pytest.mark.parametrize("question", [
    "PAN-OS 的产品文档有哪些？", "Prisma Access 产品有哪些配置？",
    "Which products have documents about GlobalProtect?", "产品文档如何更新？",
    "获取所有最近文档更新", "show all documents",
])
def test_topic_queries_still_require_search(question):
    assert not product_catalog_query(question)


@pytest.mark.asyncio
async def test_semantic_planner_selects_catalog_for_unlisted_paraphrase():
    agents = [SimpleNamespace(descriptor=AgentDescriptor(
        id=str(i), name=f"Unrelated {i}", description="specific topics",
    )) for i in range(5)]
    external = SimpleNamespace(descriptor=AgentDescriptor(
        id="external", name="External", description="external", source_type="docs",
    ))
    engine = SimpleNamespace(complete=AsyncMock(return_value=EngineResult(
        text='{"mode":"product_catalog","agent_ids":[]}',
    )))
    question = "先给我一个库内产品覆盖情况的全貌"
    assert not product_catalog_query(question)
    plan = await AgentRegistry([*agents, external]).plan(question, [], engine)
    assert plan.mode == "product_catalog" and plan.agents == agents
    assert "product_catalog" in engine.complete.call_args.args[0]


@pytest.mark.asyncio
async def test_catalog_plan_obeys_explicit_scope_and_rejects_invalid_modes():
    agents = [SimpleNamespace(descriptor=AgentDescriptor(
        id=str(i), name=str(i), description="specific topics",
    )) for i in range(5)]
    registry = AgentRegistry(agents)
    engine = SimpleNamespace(complete=AsyncMock(return_value=EngineResult(
        text='{"mode":"product_catalog","agent_ids":["1","unauthorized"]}',
    )))
    plan = await registry.plan("先给我一个库内产品覆盖情况的全貌", [], engine)
    assert plan.agents == [agents[1]]
    engine.complete.return_value = EngineResult(text='{"mode":"browse_all","agent_ids":[]}')
    with pytest.raises(ValueError):
        await registry.plan("q", [], engine)


@pytest.mark.asyncio
async def test_extraction_verifies_mentions_and_batch_local_ids():
    documents = [{
        "title": "PAN-OS deployment", "category": "", "tags": [], "summary": "config",
    }, {"title": "Guide", "category": "", "tags": ["Prisma Access"], "summary": "config"}]
    engine = SimpleNamespace(complete=AsyncMock(return_value=EngineResult(text=json.dumps({
        "products": [
            {"name": "PAN-OS", "doc_numbers": [True, 1, 1, 2, 999]},
            {"name": "pan-os", "doc_numbers": [1]},
            {"name": "GlobalProtect", "doc_numbers": [1]},
            {"name": "Prisma Access", "doc_numbers": [2]},
        ],
    }))))
    assert await extract_products(engine, documents) == {1: ["PAN-OS"], 2: ["Prisma Access"]}
    engine.complete.return_value = EngineResult(text='{"products":"all"}')
    with pytest.raises(ValueError):
        await extract_products(engine, documents)


class CatalogEngine:
    def __init__(self):
        self.pages = []
        self.route_prompts = []

    async def complete(self, prompt, **kwargs):
        if "你是知识检索路由器" in prompt:
            self.route_prompts.append(prompt)
            return EngineResult(text='{"mode":"product_catalog","agent_ids":[]}')
        assert "工作空间产品目录 Agent" in prompt
        documents = json.loads(prompt.rsplit("\n", 1)[1])["documents"]
        self.pages.append(documents)
        products = []
        for name in ["PAN-OS", "Prisma Access"]:
            numbers = [d["number"] for d in documents if name in json.dumps(d)]
            if numbers:
                products.append({"name": name, "doc_numbers": numbers})
        return EngineResult(text=json.dumps({"products": products}))

    async def complete_streaming(self, prompt, **kwargs):
        raise AssertionError("Catalog output should preserve verified counts and citations")
        yield


def document(ws, title, **kwargs):
    return Document(
        id=uuid.uuid4(), workspace_id=ws.id, title=title, storage_key=uuid.uuid4().hex,
        mime_type="text/plain", status=kwargs.pop("status", "ready"),
        created_at=datetime(2020, 1, 1), summary="configuration notes",
        content_text="BODY_SECRET_GlobalProtect", **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("semantic", [False, True])
async def test_inventory_scans_all_authorized_spaces_and_metadata_pages(
    client, seed_user, db_session, monkeypatch, stream, semantic,
):
    uid, headers = await seed_user("user")
    spaces = [Workspace(id=uuid.uuid4(), name=f"Space {i}") for i in range(5)]
    private = Workspace(id=uuid.uuid4(), name="Private")
    group = Group(id=uuid.uuid4(), name="Readers")
    db_session.add_all([*spaces, private, group])
    await db_session.flush()
    category = Category(id=uuid.uuid4(), workspace_id=spaces[1].id, name="Prisma Access")
    db_session.add(category)
    db_session.add_all([
        GroupMember(group_id=group.id, user_id=uid),
        GroupPermission(group_id=group.id, module="chat", level="read"),
        *[WorkspaceMember(workspace_id=ws.id, user_id=uid, role_in_ws="viewer") for ws in spaces],
    ])
    await db_session.flush()
    db_session.add_all([
        *[document(spaces[0], f"Guide {i}", tags=["PAN-OS"]) for i in range(85)],
        *[document(spaces[1], f"Guide B{i}", category_id=category.id) for i in range(2)],
        *[document(spaces[2], f"PAN-OS guide {i}") for i in range(2)],
        document(spaces[3], "No product label"),
        document(spaces[4], "Prisma Access guide"),
        document(private, "PRIVATE_DOCUMENT_PAN-OS"),
        document(spaces[0], "DELETED_DOCUMENT_PAN-OS", deleted_at=datetime.now().astimezone()),
        document(spaces[0], "PROCESSING_DOCUMENT_PAN-OS", status="processing"),
    ])
    await db_session.commit()
    engine = CatalogEngine()
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    response = await client.post(
        "/chat/stream" if stream else "/chat",
        json={"message": "先给我一个库内产品覆盖情况的全貌" if semantic
              else "知识库里有哪些产品的文档？"}, headers=headers,
    )
    assert response.status_code == 200
    if stream:
        done = [block for block in response.text.split("\n\n") if "event: done\n" in block][-1]
        body = json.loads(next(s[6:] for s in done.splitlines() if s.startswith("data: ")))
    else:
        body = response.json()
    assert body.get("error_key") is None
    assert len(body["agent_runs"]) == 5
    assert len(engine.route_prompts) == int(semantic)
    assert all("Guide" not in prompt for prompt in engine.route_prompts)
    assert len(engine.pages) == 7
    assert sum(len(page) for page in engine.pages) == 91
    assert all(len(page) <= 40 for page in engine.pages)
    serialized = json.dumps(engine.pages)
    for secret in ["BODY_SECRET", "PRIVATE_DOCUMENT", "DELETED_DOCUMENT", "PROCESSING_DOCUMENT"]:
        assert secret not in serialized
    assert "识别到 2 个产品名称" in body["answer"]
    assert "**PAN-OS**：87 篇文档" in body["answer"]
    assert "**Prisma Access**：3 篇文档" in body["answer"]
    assert "未识别具体产品" in body["answer"]
    assert len(body["sources"]) == 5
    assert sum(source["document_count"] for source in body["sources"]) == 91
    for source in body["sources"]:
        assert source["content_kind"] == "document_catalog"
        assert f'[{source["citation_id"]}]' in body["answer"]
        assert source["workspace_id"] in {str(ws.id) for ws in spaces}
    history = (await client.get(
        f'/conversations/{body["conversation_id"]}', headers=headers,
    )).json()
    saved = next(m for m in reversed(history["messages"]) if m["role"] == "assistant")
    assert saved["sources"] == body["sources"]
    assert saved["retrieval"]["agent_runs"] == body["agent_runs"]
    filtered = await client.post("/chat", json={
        "message": "知识库里有哪些产品的文档？", "agent_ids": [f"workspace:{spaces[4].id}"],
    }, headers=headers)
    assert filtered.status_code == 200
    assert len(filtered.json()["sources"]) == 1
    assert filtered.json()["sources"][0]["product"] == "Prisma Access"


@pytest.mark.asyncio
async def test_empty_catalog_and_failed_extraction_report_scope(db_session, monkeypatch):
    spaces = [Workspace(id=uuid.uuid4(), name="Empty"), Workspace(id=uuid.uuid4(), name="Failed")]
    db_session.add_all(spaces)
    await db_session.flush()
    db_session.add(document(spaces[1], "PAN-OS"))
    await db_session.commit()
    engine = SimpleNamespace(complete=AsyncMock(return_value=EngineResult(text="invalid JSON")))
    monkeypatch.setattr(answer_service, "get_chat_engine", AsyncMock(return_value=engine))
    result = await answer_service.answer_question(
        db_session, workspace_id=[s.id for s in spaces], question="知识库里有哪些产品的文档？",
        history=[("assistant", "PAN-OS docs exist [S1]")],
    )
    assert result.error_key is None and result.sources == []
    assert "以下目录不完整" in result.answer
    assert {r["status"] for r in result.agent_runs} == {"done", "failed"}
