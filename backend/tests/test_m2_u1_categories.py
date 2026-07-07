"""M2-U1：分类体系 CRUD。管理员维护，隔离 + 层级。"""

import pytest

pytestmark = pytest.mark.asyncio


async def _make_ws(client, admin_headers, name="ws"):
    resp = await client.post("/workspaces", json={"name": name}, headers=admin_headers)
    return resp.json()["id"]


async def test_admin_creates_category(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws_id = await _make_ws(client, admin_headers)
    resp = await client.post(
        f"/categories?workspace_id={ws_id}",
        json={"name": "产品文档"},
        headers=admin_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "产品文档"
    assert body["workspace_id"] == ws_id
    assert body["parent_id"] is None


async def test_create_child_category(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws_id = await _make_ws(client, admin_headers)
    parent = await client.post(
        f"/categories?workspace_id={ws_id}",
        json={"name": "大类"},
        headers=admin_headers,
    )
    parent_id = parent.json()["id"]
    child = await client.post(
        f"/categories?workspace_id={ws_id}",
        json={"name": "子类", "parent_id": parent_id},
        headers=admin_headers,
    )
    assert child.status_code == 201
    assert child.json()["parent_id"] == parent_id


async def test_non_admin_cannot_create_category(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws_id = await _make_ws(client, admin_headers)
    _, internal_headers = await seed_user("internal")
    resp = await client.post(
        f"/categories?workspace_id={ws_id}",
        json={"name": "x"},
        headers=internal_headers,
    )
    assert resp.status_code == 403


async def test_admin_non_member_cannot_create_category(client, seed_user):
    """管理员但非该空间成员，仍无权在其内建分类。"""
    _, admin_a = await seed_user("admin")
    ws_id = await _make_ws(client, admin_a)
    _, admin_b = await seed_user("admin")  # 另一管理员，未加入 ws
    resp = await client.post(
        f"/categories?workspace_id={ws_id}",
        json={"name": "x"},
        headers=admin_b,
    )
    assert resp.status_code == 403


async def test_list_categories(client, seed_user):
    _, admin_headers = await seed_user("admin")
    ws_id = await _make_ws(client, admin_headers)
    await client.post(
        f"/categories?workspace_id={ws_id}", json={"name": "A"}, headers=admin_headers
    )
    await client.post(
        f"/categories?workspace_id={ws_id}", json={"name": "B"}, headers=admin_headers
    )
    resp = await client.get(f"/categories?workspace={ws_id}", headers=admin_headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 2


async def test_invalid_parent_returns_400(client, seed_user):
    import uuid

    _, admin_headers = await seed_user("admin")
    ws_id = await _make_ws(client, admin_headers)
    resp = await client.post(
        f"/categories?workspace_id={ws_id}",
        json={"name": "x", "parent_id": str(uuid.uuid4())},
        headers=admin_headers,
    )
    assert resp.status_code == 400
