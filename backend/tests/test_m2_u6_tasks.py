"""M2-U6：任务可观测端点 tasks / reprocess。"""

import io
import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _ws_and_upload(client, admin_headers):
    ws = await client.post("/workspaces", json={"name": "ws"}, headers=admin_headers)
    ws_id = ws.json()["id"]
    up = await client.post(
        f"/workspaces/{ws_id}/documents",
        files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
        headers=admin_headers,
    )
    return ws_id, up.json()["id"]


async def test_list_tasks_returns_task(client, seed_user):
    _, admin_headers = await seed_user("admin")
    _, doc_id = await _ws_and_upload(client, admin_headers)
    resp = await client.get(f"/documents/{doc_id}/tasks", headers=admin_headers)
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) >= 1
    assert tasks[0]["document_id"] == doc_id
    assert "status" in tasks[0] and "logs" in tasks[0]


async def test_list_tasks_non_member_404(client, seed_user):
    _, admin_headers = await seed_user("admin")
    _, doc_id = await _ws_and_upload(client, admin_headers)
    _, other = await seed_user("internal")
    resp = await client.get(f"/documents/{doc_id}/tasks", headers=other)
    assert resp.status_code == 404  # 不泄漏存在性


async def test_reprocess_creates_new_task(client, seed_user):
    _, admin_headers = await seed_user("admin")
    _, doc_id = await _ws_and_upload(client, admin_headers)
    resp = await client.post(
        f"/documents/{doc_id}/reprocess", headers=admin_headers
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "queued"

    tasks = await client.get(f"/documents/{doc_id}/tasks", headers=admin_headers)
    assert len(tasks.json()) >= 2  # 原任务 + reprocess 任务


async def test_reprocess_requires_admin(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws_id, doc_id = await _ws_and_upload(client, admin_headers)
    internal_id, internal_headers = await seed_user("internal")
    await client.post(
        f"/workspaces/{ws_id}/members",
        json={"user_id": str(internal_id), "role_in_ws": "editor"},
        headers=admin_headers,
    )
    resp = await client.post(
        f"/documents/{doc_id}/reprocess", headers=internal_headers
    )
    assert resp.status_code == 403


async def test_tasks_unknown_document_404(client, seed_user):
    _, admin_headers = await seed_user("admin")
    resp = await client.get(
        f"/documents/{uuid.uuid4()}/tasks", headers=admin_headers
    )
    assert resp.status_code == 404
