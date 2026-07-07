"""M2-U2：documents / processing_tasks 表可映射到真实 DB，含 GIN 索引与约束。"""

import uuid

import pytest
from sqlalchemy import text

from app.models.auth import Workspace
from app.models.document import Document, ProcessingTask

pytestmark = pytest.mark.asyncio


async def test_document_and_task_roundtrip(db_session):
    ws = Workspace(id=uuid.uuid4(), name="ws")
    db_session.add(ws)
    await db_session.commit()

    doc = Document(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        title="a.pdf",
        storage_key=f"{ws.id}/{uuid.uuid4()}",
        mime_type="application/pdf",
        status="processing",
    )
    db_session.add(doc)
    await db_session.commit()

    task = ProcessingTask(id=uuid.uuid4(), document_id=doc.id, kind="classify")
    db_session.add(task)
    await db_session.commit()

    assert doc.tags == []
    assert task.status == "queued"
    assert task.attempts == 0
    assert task.max_attempts == 3


async def test_gin_index_exists(db_session):
    result = await db_session.execute(
        text("SELECT indexname FROM pg_indexes WHERE tablename = 'documents'")
    )
    names = {row[0] for row in result.all()}
    assert "ix_documents_search_tsv" in names


async def test_status_check_constraint(db_session):
    ws = Workspace(id=uuid.uuid4(), name="ws")
    db_session.add(ws)
    await db_session.commit()
    with pytest.raises(Exception):  # noqa: B017,PT011  # CHECK 违约
        await db_session.execute(
            text(
                "INSERT INTO documents (id, workspace_id, title, storage_key, "
                "mime_type, status) VALUES (uuid_generate_v4(), :ws, 't', 'k', "
                "'text/plain', 'bogus')"
            ),
            {"ws": str(ws.id)},
        )
        await db_session.commit()
