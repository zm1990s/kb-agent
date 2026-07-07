"""M3-U3：答案生成，用假引擎替换 CLI。"""

import uuid

import pytest
from sqlalchemy import func, update

from app.engine.base import EngineResult
from app.models.auth import Workspace
from app.models.document import Document
from app.services import answer_service
from app.services.answer_service import NO_MATCH_ANSWER, answer_question

pytestmark = pytest.mark.asyncio


class _FakeEngine:
    def __init__(self, text):
        self._text = text
        self.called = False

    async def complete(self, prompt, *, files=None, system=None):
        self.called = True
        self.last_prompt = prompt
        return EngineResult(text=self._text)


async def _ready_doc(session, ws_id, *, title, content):
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        title=title,
        storage_key=f"{ws_id}/{uuid.uuid4().hex}",
        mime_type="text/plain",
        content_text=content,
        status="ready",
    )
    session.add(doc)
    await session.commit()
    await session.execute(
        update(Document)
        .where(Document.id == doc.id)
        .values(search_tsv=func.to_tsvector("simple", func.concat_ws(" ", title, content)))
    )
    await session.commit()
    return doc


async def test_answer_with_hit_returns_answer_and_sources(db_session, monkeypatch):
    ws = Workspace(id=uuid.uuid4(), name="ws")
    db_session.add(ws)
    await db_session.commit()
    doc = await _ready_doc(db_session, ws.id, title="防火墙指南", content="firewall policy")

    fake = _FakeEngine("根据文档，防火墙策略如下……")
    monkeypatch.setattr(answer_service, "get_engine", lambda: fake)

    res = await answer_question(db_session, workspace_id=ws.id, question="firewall")
    assert fake.called
    assert res.answer == "根据文档，防火墙策略如下……"
    assert len(res.sources) == 1
    assert res.sources[0]["doc_id"] == str(doc.id)
    assert res.sources[0]["title"] == "防火墙指南"
    assert "download" in res.sources[0]["download_url"]


async def test_answer_no_hit_does_not_call_engine(db_session, monkeypatch):
    ws = Workspace(id=uuid.uuid4(), name="ws")
    db_session.add(ws)
    await db_session.commit()

    fake = _FakeEngine("不应被调用")
    monkeypatch.setattr(answer_service, "get_engine", lambda: fake)

    res = await answer_question(db_session, workspace_id=ws.id, question="nonexistent")
    # 无命中：不编造、不调用引擎
    assert res.answer == NO_MATCH_ANSWER
    assert res.sources == []
    assert fake.called is False
