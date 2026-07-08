"""F1：目录移动（改层级）+ 防环。"""


import pytest

pytestmark = pytest.mark.asyncio


async def _ws(client, headers):
    return (await client.post("/workspaces", json={"name": "ws"}, headers=headers)).json()["id"]


async def _folder(client, headers, ws_id, name, parent=None):
    body = {"name": name}
    if parent:
        body["parent_id"] = parent
    r = await client.post(f"/folders?workspace_id={ws_id}", json=body, headers=headers)
    return r.json()["id"]


async def test_move_folder_changes_parent(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    a = await _folder(client, admin, ws_id, "A")
    b = await _folder(client, admin, ws_id, "B")

    # 把 B 移到 A 下
    resp = await client.patch(
        f"/folders/{b}/move?workspace_id={ws_id}",
        json={"parent_id": a},
        headers=admin,
    )
    assert resp.status_code == 200
    assert resp.json()["parent_id"] == a

    # 再移回顶级
    resp2 = await client.patch(
        f"/folders/{b}/move?workspace_id={ws_id}",
        json={"parent_id": None},
        headers=admin,
    )
    assert resp2.json()["parent_id"] is None


async def test_move_folder_rejects_cycle(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    a = await _folder(client, admin, ws_id, "A")
    child = await _folder(client, admin, ws_id, "child", parent=a)

    # 把 A 移到它自己的子目录 child 下 -> 成环 -> 400
    resp = await client.patch(
        f"/folders/{a}/move?workspace_id={ws_id}",
        json={"parent_id": child},
        headers=admin,
    )
    assert resp.status_code == 400

    # 移到自身 -> 400
    resp2 = await client.patch(
        f"/folders/{a}/move?workspace_id={ws_id}",
        json={"parent_id": a},
        headers=admin,
    )
    assert resp2.status_code == 400


async def test_move_folder_non_member_403(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    a = await _folder(client, admin, ws_id, "A")
    _, other = await seed_user("internal")
    resp = await client.patch(
        f"/folders/{a}/move?workspace_id={ws_id}",
        json={"parent_id": None},
        headers=other,
    )
    assert resp.status_code == 403
