"""M2-U5：归类 worker。用假引擎替换 Claude CLI，测成功/失败/重试。"""

import uuid

import pytest

from app.engine.base import EngineResult
from app.models.auth import Workspace
from app.models.document import Category, Document, ProcessingTask
from app.services import classify_service

pytestmark = pytest.mark.asyncio


class _FakeEngine:
    def __init__(self, text: str):
        self._text = text

    async def complete(self, prompt, *, files=None, system=None):
        return EngineResult(text=self._text)


class _BoomEngine:
    async def complete(self, prompt, *, files=None, system=None):
        raise RuntimeError("engine down")


async def _seed_doc(session, *, with_category=True):
    ws = Workspace(id=uuid.uuid4(), name="ws")
    session.add(ws)
    await session.flush()
    if with_category:
        session.add(Category(id=uuid.uuid4(), workspace_id=ws.id, name="产品文档"))
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        title="spec.pdf",
        storage_key=f"{ws.id}/{uuid.uuid4().hex}",
        mime_type="application/pdf",
        status="processing",
    )
    session.add(doc)
    task = ProcessingTask(id=uuid.uuid4(), document_id=doc.id, kind="classify")
    session.add(task)
    await session.commit()
    # 写一个原文文件，供 engine「读取」（假引擎实际不读，但 open_path 需存在）
    from app.storage.base import get_storage

    await get_storage().save(doc.storage_key, b"dummy content")
    return ws, doc, task


async def test_classification_success(db_session, monkeypatch):
    ws, doc, task = await _seed_doc(db_session)
    fake = _FakeEngine(
        '{"category": "产品文档", "summary": "一份产品规格", '
        '"tags": ["产品", "规格"], "content_text": "全文内容"}'
    )
    monkeypatch.setattr(classify_service, "get_engine", lambda *a, **k: fake)

    await classify_service.run_classification(db_session, task.id)

    await db_session.refresh(doc)
    await db_session.refresh(task)
    assert doc.status == "ready"
    assert doc.summary == "一份产品规格"
    assert doc.tags == ["产品", "规格"]
    assert doc.content_text == "全文内容"
    assert doc.category_id is not None  # 分类名解析成功
    assert task.status == "succeeded"
    assert task.attempts == 1


async def test_classification_unknown_category_sets_null(db_session, monkeypatch):
    ws, doc, task = await _seed_doc(db_session)
    fake = _FakeEngine(
        '{"category": "不存在的类", "summary": "s", "tags": ["a"], '
        '"content_text": "t"}'
    )
    monkeypatch.setattr(classify_service, "get_engine", lambda *a, **k: fake)

    await classify_service.run_classification(db_session, task.id)
    await db_session.refresh(doc)
    assert doc.status == "ready"
    assert doc.category_id is None


async def test_classification_bad_json_fails_and_records_error(db_session, monkeypatch):
    ws, doc, task = await _seed_doc(db_session)
    monkeypatch.setattr(
        classify_service, "get_engine", lambda *a, **k: _FakeEngine("not json at all")
    )

    await classify_service.run_classification(db_session, task.id)
    await db_session.refresh(doc)
    await db_session.refresh(task)
    assert doc.status == "failed"
    assert task.status == "failed"
    assert task.error  # 记录了错误
    assert any(log["stage"] == "error" for log in task.logs)


async def test_classification_engine_failure_is_retriable(db_session, monkeypatch):
    ws, doc, task = await _seed_doc(db_session)
    monkeypatch.setattr(classify_service, "get_engine", lambda *a, **k: _BoomEngine())

    # 第一次失败
    await classify_service.run_classification(db_session, task.id)
    await db_session.refresh(task)
    assert task.status == "failed"
    assert task.attempts == 1

    # 重试：换成功引擎，再跑一次同一 task
    fake = _FakeEngine(
        '{"category": null, "summary": "s", "tags": ["a"], "content_text": "t"}'
    )
    monkeypatch.setattr(classify_service, "get_engine", lambda *a, **k: fake)
    await classify_service.run_classification(db_session, task.id)
    await db_session.refresh(doc)
    await db_session.refresh(task)
    assert task.status == "succeeded"
    assert task.attempts == 2
    assert doc.status == "ready"
