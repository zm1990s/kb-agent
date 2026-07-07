"""M2-U4：文档上传端点。"""

import io
import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _make_ws(client, admin_headers, name="ws"):
    resp = await client.post("/workspaces", json={"name": name}, headers=admin_headers)
    return resp.json()["id"]


def _file(content=b"hello world", name="doc.txt", mime="text/plain"):
    return {"file": (name, io.BytesIO(content), mime)}


async def test_upload_returns_202_processing(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws_id = await _make_ws(client, admin_headers)
    resp = await client.post(
        f"/workspaces/{ws_id}/documents", files=_file(), headers=admin_headers
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "processing"
    assert "id" in body and "task_id" in body


async def test_upload_requires_admin(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws_id = await _make_ws(client, admin_headers)
    # 把一个 internal 用户加入空间，但其非 admin
    internal_id, internal_headers = await seed_user("internal")
    await client.post(
        f"/workspaces/{ws_id}/members",
        json={"user_id": str(internal_id), "role_in_ws": "editor"},
        headers=admin_headers,
    )
    resp = await client.post(
        f"/workspaces/{ws_id}/documents", files=_file(), headers=internal_headers
    )
    assert resp.status_code == 403


async def test_upload_non_member_admin_403(client, seed_user):
    """管理员但非该空间成员，不能上传（越权防护）。"""
    _, admin_a = await seed_user("admin")
    ws_id = await _make_ws(client, admin_a)
    _, admin_b = await seed_user("admin")  # 未加入 ws
    resp = await client.post(
        f"/workspaces/{ws_id}/documents", files=_file(), headers=admin_b
    )
    assert resp.status_code == 403


async def test_upload_requires_auth(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws_id = await _make_ws(client, admin_headers)
    resp = await client.post(f"/workspaces/{ws_id}/documents", files=_file())
    assert resp.status_code == 401


async def test_upload_unknown_workspace_403(client, seed_user):
    _, admin_headers = await seed_user("admin")
    resp = await client.post(
        f"/workspaces/{uuid.uuid4()}/documents", files=_file(), headers=admin_headers
    )
    assert resp.status_code == 403
