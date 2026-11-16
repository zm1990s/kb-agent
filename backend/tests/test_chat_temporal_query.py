"""Upload-history intent boundaries, calendar intervals and authorized SQL results."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, text

from app.models.auth import Workspace, WorkspaceMember
from app.models.document import Document
from app.models.rbac import Group, GroupMember, GroupPermission
from app.services import answer_service
from app.services.temporal_query_service import document_updates_query

NOW = datetime(2026, 11, 6, 4, 0, tzinfo=UTC)  # Friday noon in Shanghai.


@pytest.mark.parametrize(
    "question",
    [
        "最新 PAN-OS 配置怎么做？",
        "最新的 GlobalProtect 文档有哪些配置变化？",
        "How do I configure the new feature in PAN-OS?",
        "latest PAN-OS configuration documents",
        "What is new in the community?",
        "解释文档里的更新时间字段",
    ],
)
def test_product_configuration_is_not_upload_history(question):
    assert document_updates_query(question, now=NOW) is None


@pytest.mark.parametrize(
    ("question", "since", "until"),
    [
        ("最近上传了什么？", NOW - timedelta(days=7), NOW),
        ("今天上传了什么文件？", datetime(2026, 11, 5, 16, tzinfo=UTC), NOW),
        (
            "昨天有哪些新文档？",
            datetime(2026, 11, 4, 16, tzinfo=UTC),
            datetime(2026, 11, 5, 16, tzinfo=UTC),
        ),
        ("本周有哪些新文档？", datetime(2026, 11, 1, 16, tzinfo=UTC), NOW),
        (
            "List documents uploaded last week",
            datetime(2026, 10, 25, 16, tzinfo=UTC),
            datetime(2026, 11, 1, 16, tzinfo=UTC),
        ),
        ("documents uploaded in the past 3 days", NOW - timedelta(days=3), NOW),
    ],
)
def test_explicit_calendar_bounds(question, since, until):
    query = document_updates_query(question, now=NOW)
    assert query is not None
    assert query.since == since and query.until == until


@pytest.mark.asyncio
@pytest.mark.parametrize("timezone_column", [False, True])
async def test_sql_upload_history_counts_limits_sources_and_permissions(
    client,
    seed_user,
    db_session,
    db_engine,
    monkeypatch,
    timezone_column,
):
    uid, headers = await seed_user("user")
    ws = Workspace(id=uuid.uuid4(), name="Space")
    private = Workspace(id=uuid.uuid4(), name="Private")
    group = Group(id=uuid.uuid4(), name="Chat users")
    db_session.add_all([ws, private, group])
    await db_session.flush()
    db_session.add_all(
        [
            GroupMember(group_id=group.id, user_id=uid),
            GroupPermission(group_id=group.id, module="chat", level="read"),
            WorkspaceMember(workspace_id=ws.id, user_id=uid, role_in_ws="viewer"),
        ]
    )

    def doc(workspace, title, when, **kwargs):
        return Document(
            workspace_id=workspace.id,
            title=title,
            storage_key=uuid.uuid4().hex,
            mime_type="text/plain",
            status="ready",
            created_at=when.replace(tzinfo=None),
            content_text="SECRET_BODY",
            **kwargs,
        )

    db_session.add_all([doc(ws, f"Public {n}", NOW - timedelta(minutes=n + 1)) for n in range(25)])
    db_session.add_all(
        [
            doc(private, "PRIVATE", NOW - timedelta(minutes=1)),
            doc(ws, "OLD", NOW - timedelta(days=9)),
            doc(ws, "FUTURE", NOW + timedelta(days=1)),
            doc(ws, "DELETED", NOW - timedelta(minutes=1), deleted_at=NOW),
        ]
    )
    await db_session.commit()
    if timezone_column:
        await db_session.execute(
            text(
                "ALTER TABLE documents ALTER COLUMN created_at TYPE "
                "timestamptz USING created_at AT TIME ZONE 'UTC'"
            )
        )
        await db_session.commit()
    monkeypatch.setattr(
        answer_service, "document_updates_query", lambda q: document_updates_query(q, now=NOW)
    )
    engine_factory = AsyncMock(side_effect=AssertionError("Upload history must not call an LLM"))
    monkeypatch.setattr(answer_service, "get_chat_engine", engine_factory)
    queries = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)

    event.listen(db_engine.sync_engine, "before_cursor_execute", capture)
    try:
        response = await client.post(
            "/chat", json={"message": "本周有哪些新文档？"}, headers=headers
        )
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", capture)
    body = response.json()
    assert response.status_code == 200 and body["error_key"] is None
    assert len(body["sources"]) == 20
    assert "找到 25 篇文档，列出 20 篇" in body["answer"]
    assert body["sources"][0]["title"] == "Public 0"
    assert all(s["workspace_id"] == str(ws.id) for s in body["sources"])
    assert body["agent_runs"][0]["document_count"] == 25
    assert not any("documents.content_text" in q for q in queries)
    response = await client.post(
        "/chat/stream",
        json={
            "message": "获取所有最近文档更新",
        },
        headers=headers,
    )
    import json

    done = [
        json.loads(block.split("data: ", 1)[1])
        for block in response.text.split("\n\n")
        if block.startswith("event: done")
    ][0]
    assert len(done["sources"]) == 25
    assert "不代表原文件的修改时间" in done["answer"]
    engine_factory.assert_not_called()
    response = await client.post(
        "/chat",
        json={
            "message": "昨天有哪些新文档？",
        },
        headers=headers,
    )
    assert response.json()["sources"] == [] and response.json()["error_key"] is None
