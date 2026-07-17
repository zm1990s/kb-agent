"""M3-U3/U7：Agent 式索引问答。Claude 基于全空间索引作答并选相关文档。"""

import json
import uuid

import pytest

from app.engine.base import EngineResult, TextChunk
from app.models.auth import Workspace
from app.models.document import Document
from app.services import answer_service
from app.services.answer_service import NO_DOCS_ANSWER, answer_question

pytestmark = pytest.mark.asyncio


class _FakeEngine:
    """按预设 JSON 回应；记录收到的 catalog 以便断言。"""

    def __init__(self, answer="这是答案", doc_numbers=None):
        self._answer = answer
        self._phase1_payload = json.dumps({"doc_numbers": doc_numbers or []})
        self.called = False
        self.last_prompt = None

    async def complete(self, prompt, *, files=None, system=None):
        # Phase 1：返回包含 doc_numbers 的 JSON
        self.called = True
        self.last_prompt = prompt
        return EngineResult(text=self._phase1_payload)

    async def complete_streaming(self, prompt, *, system=None, files=None):
        # Phase 2：yield 纯文本答案
        self.last_prompt = prompt
        yield TextChunk(text=self._answer)


async def _ready_doc(session, ws_id, *, title, summary="摘要", tags=None):
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        title=title,
        storage_key=f"{ws_id}/{uuid.uuid4().hex}",
        mime_type="text/plain",
        summary=summary,
        tags=tags or ["标签"],
        content_text="正文",
        status="ready",
    )
    session.add(doc)
    await session.commit()
    return doc


async def test_answer_feeds_full_index_and_selects_docs(db_session, monkeypatch):
    ws = Workspace(id=uuid.uuid4(), name="ws")
    db_session.add(ws)
    await db_session.commit()
    await _ready_doc(db_session, ws.id, title="防火墙配置指南")
    await _ready_doc(db_session, ws.id, title="报销流程")

    # Claude 选中第 1 篇（索引按 created_at 倒序，[1] 为最新创建的“报销流程”）
    fake = _FakeEngine(answer="防火墙这样配置……", doc_numbers=[1])
    async def _engine(*a, **k): return fake
    monkeypatch.setattr(answer_service, "get_chat_engine", _engine)

    res = await answer_question(db_session, workspace_id=ws.id, question="防火墙怎么配")
    assert fake.called
    # 全空间索引都进了 prompt（两篇标题都在）
    assert "防火墙配置指南" in fake.last_prompt
    assert "报销流程" in fake.last_prompt
    assert res.answer == "防火墙这样配置……"
    # 编号 1 映射为一个可下载来源（编号→真实文档由服务端控制）
    assert len(res.sources) == 1
    assert res.sources[0]["title"] == "报销流程"
    assert "download" in res.sources[0]["download_url"]


async def test_answer_no_docs_selected_returns_no_sources(db_session, monkeypatch):
    ws = Workspace(id=uuid.uuid4(), name="ws")
    db_session.add(ws)
    await db_session.commit()
    await _ready_doc(db_session, ws.id, title="报销流程")

    fake = _FakeEngine(answer="没有找到防火墙相关文档。", doc_numbers=[])
    async def _engine(*a, **k): return fake
    monkeypatch.setattr(answer_service, "get_chat_engine", _engine)

    res = await answer_question(db_session, workspace_id=ws.id, question="防火墙")
    assert res.answer == "没有找到防火墙相关文档。"
    assert res.sources == []


async def test_answer_empty_workspace_no_history(db_session, monkeypatch):
    ws = Workspace(id=uuid.uuid4(), name="empty")
    db_session.add(ws)
    await db_session.commit()

    fake = _FakeEngine()
    async def _engine(*a, **k): return fake
    monkeypatch.setattr(answer_service, "get_chat_engine", _engine)

    res = await answer_question(db_session, workspace_id=ws.id, question="任意问题")
    # 空间无文档且无历史：不调用引擎，直接提示
    assert res.answer == NO_DOCS_ANSWER
    assert fake.called is False


async def test_answer_hallucinated_doc_number_ignored(db_session, monkeypatch):
    """Claude 返回越界编号时，服务端忽略（防 ID 幻觉）。"""
    ws = Workspace(id=uuid.uuid4(), name="ws")
    db_session.add(ws)
    await db_session.commit()
    await _ready_doc(db_session, ws.id, title="唯一文档")

    fake = _FakeEngine(answer="见文档", doc_numbers=[99])  # 越界
    async def _engine(*a, **k): return fake
    monkeypatch.setattr(answer_service, "get_chat_engine", _engine)

    res = await answer_question(db_session, workspace_id=ws.id, question="q")
    assert res.sources == []  # 越界编号被丢弃
