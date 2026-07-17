"""M1-U6：空间 CRUD + 成员，重点验证隔离。"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def test_admin_creates_workspace(client, seed_user):
    _, admin_headers = await seed_user("admin")
    resp = await client.post(
        "/workspaces", json={"name": "空间A", "description": "desc"}, headers=admin_headers
    )
    assert resp.status_code == 201
    assert resp.json()["name"] == "空间A"


async def test_non_admin_cannot_create_workspace(client, seed_user):
    _, internal_headers = await seed_user("user")
    resp = await client.post(
        "/workspaces", json={"name": "空间B"}, headers=internal_headers
    )
    assert resp.status_code == 403


async def test_create_requires_auth(client):
    resp = await client.post("/workspaces", json={"name": "空间C"})
    assert resp.status_code == 401


async def test_creator_sees_own_workspace(client, seed_user):
    _, admin_headers = await seed_user("admin")
    await client.post("/workspaces", json={"name": "我的空间"}, headers=admin_headers)
    resp = await client.get("/workspaces", headers=admin_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "我的空间"
    assert body[0]["role_in_ws"] == "owner"


async def test_partner_cannot_see_unauthorized_workspace(client, seed_user):
    """隔离核心：Partner 看不到别人建的、未授权的空间。"""
    _, admin_headers = await seed_user("admin")
    await client.post("/workspaces", json={"name": "内部空间"}, headers=admin_headers)

    _, partner_headers = await seed_user("user")
    resp = await client.get("/workspaces", headers=partner_headers)
    assert resp.status_code == 200
    assert resp.json() == []  # 未被授权，看不到任何空间


async def test_add_member_grants_visibility(client, seed_user):
    """加成员后，被加者能看到该空间。"""
    _, admin_headers = await seed_user("admin")
    ws = await client.post(
        "/workspaces", json={"name": "共享空间"}, headers=admin_headers
    )
    ws_id = ws.json()["id"]

    partner_id, partner_headers = await seed_user("user")
    add = await client.post(
        f"/workspaces/{ws_id}/members",
        json={"user_id": str(partner_id), "role_in_ws": "viewer"},
        headers=admin_headers,
    )
    assert add.status_code == 201

    resp = await client.get("/workspaces", headers=partner_headers)
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == ws_id
    assert body[0]["role_in_ws"] == "viewer"


async def test_non_admin_cannot_add_member(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws = await client.post("/workspaces", json={"name": "空间X"}, headers=admin_headers)
    ws_id = ws.json()["id"]

    _, internal_headers = await seed_user("user")
    resp = await client.post(
        f"/workspaces/{ws_id}/members",
        json={"user_id": str(uuid.uuid4()), "role_in_ws": "viewer"},
        headers=internal_headers,
    )
    assert resp.status_code == 403


async def test_add_member_unknown_workspace_404(client, seed_user):
    _, admin_headers = await seed_user("admin")
    partner_id, _ = await seed_user("user")
    resp = await client.post(
        f"/workspaces/{uuid.uuid4()}/members",
        json={"user_id": str(partner_id), "role_in_ws": "viewer"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


async def test_add_duplicate_member_409(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws = await client.post("/workspaces", json={"name": "空间Y"}, headers=admin_headers)
    ws_id = ws.json()["id"]
    partner_id, _ = await seed_user("user")
    payload = {"user_id": str(partner_id), "role_in_ws": "viewer"}
    first = await client.post(
        f"/workspaces/{ws_id}/members", json=payload, headers=admin_headers
    )
    assert first.status_code == 201
    second = await client.post(
        f"/workspaces/{ws_id}/members", json=payload, headers=admin_headers
    )
    assert second.status_code == 409
