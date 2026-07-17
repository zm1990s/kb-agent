"""M2-U10：目录 CRUD + 文档删除/移动/替换。"""

import io
import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def _ws(client, headers):
    return (await client.post("/workspaces", json={"name": "ws"}, headers=headers)).json()["id"]


def _file(content=b"hello", name="a.txt", mime="text/plain"):
    return {"file": (name, io.BytesIO(content), mime)}


async def _upload(client, headers, ws_id, folder_id=None):
    data = {"folder_id": folder_id} if folder_id else {}
    r = await client.post(
        f"/workspaces/{ws_id}/documents", files=_file(), data=data, headers=headers
    )
    return r


# ── 目录 CRUD ──────────────────────────────────────────


async def test_folder_crud(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)

    # 建
    created = await client.post(
        f"/folders?workspace_id={ws_id}", json={"name": "方案库"}, headers=admin
    )
    assert created.status_code == 201
    fid = created.json()["id"]

    # 子目录
    child = await client.post(
        f"/folders?workspace_id={ws_id}",
        json={"name": "防火墙", "parent_id": fid},
        headers=admin,
    )
    assert child.status_code == 201
    assert child.json()["parent_id"] == fid

    # 列表
    lst = await client.get(f"/folders?workspace={ws_id}", headers=admin)
    assert lst.status_code == 200
    assert len(lst.json()) == 2

    # 改名
    rn = await client.patch(
        f"/folders/{fid}?workspace_id={ws_id}", json={"name": "方案资料"}, headers=admin
    )
    assert rn.status_code == 200
    assert rn.json()["name"] == "方案资料"

    # 删除
    dele = await client.delete(f"/folders/{fid}?workspace_id={ws_id}", headers=admin)
    assert dele.status_code == 204


async def test_folder_non_member_403(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    _, other = await seed_user("user")
    resp = await client.get(f"/folders?workspace={ws_id}", headers=other)
    assert resp.status_code == 403


# ── 文档移动 ───────────────────────────────────────────


async def test_move_document_into_folder(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    fid = (
        await client.post(
            f"/folders?workspace_id={ws_id}", json={"name": "F"}, headers=admin
        )
    ).json()["id"]
    doc_id = (await _upload(client, admin, ws_id)).json()["id"]

    mv = await client.patch(
        f"/documents/{doc_id}/move", json={"folder_id": fid}, headers=admin
    )
    assert mv.status_code == 200
    assert mv.json()["folder_id"] == fid

    # 按目录过滤能查到
    listed = await client.get(
        f"/workspaces/{ws_id}/documents?folder={fid}", headers=admin
    )
    assert any(d["id"] == doc_id for d in listed.json())

    # 移出目录
    out = await client.patch(
        f"/documents/{doc_id}/move", json={"folder_id": None}, headers=admin
    )
    assert out.json()["folder_id"] is None


async def test_move_to_foreign_folder_400(client, seed_user):
    _, admin = await seed_user("admin")
    ws_a = await _ws(client, admin)
    ws_b = await _ws(client, admin)
    doc_id = (await _upload(client, admin, ws_a)).json()["id"]
    foreign_fid = (
        await client.post(
            f"/folders?workspace_id={ws_b}", json={"name": "B"}, headers=admin
        )
    ).json()["id"]
    resp = await client.patch(
        f"/documents/{doc_id}/move", json={"folder_id": foreign_fid}, headers=admin
    )
    assert resp.status_code == 400


# ── 文档删除 ───────────────────────────────────────────


async def test_delete_document(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    doc_id = (await _upload(client, admin, ws_id)).json()["id"]

    dele = await client.delete(f"/documents/{doc_id}", headers=admin)
    assert dele.status_code == 204

    # 删除后查不到（404，不泄漏存在性）
    got = await client.get(f"/documents/{doc_id}", headers=admin)
    assert got.status_code == 404


async def test_delete_requires_admin(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    doc_id = (await _upload(client, admin, ws_id)).json()["id"]
    internal_id, internal = await seed_user("user")
    await client.post(
        f"/workspaces/{ws_id}/members",
        json={"user_id": str(internal_id), "role_in_ws": "editor"},
        headers=admin,
    )
    resp = await client.delete(f"/documents/{doc_id}", headers=internal)
    assert resp.status_code == 403


# ── 文档替换 ───────────────────────────────────────────


async def test_replace_document_content(client, seed_user, db_session):
    from app.models.document import Document

    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    doc_id = (await _upload(client, admin, ws_id)).json()["id"]

    # 手动把文档标记 ready 以模拟已归类
    doc = await db_session.get(Document, uuid.UUID(doc_id))
    doc.status = "ready"
    doc.summary = "旧摘要"
    doc.tags = ["旧"]
    await db_session.commit()

    resp = await client.post(
        f"/documents/{doc_id}/replace",
        files=_file(content=b"new content", name="v2.txt"),
        headers=admin,
    )
    assert resp.status_code == 202
    assert resp.json()["status"] == "processing"

    # 替换后：标题更新、状态回 processing、旧元数据清空
    await db_session.refresh(doc)
    assert doc.title == "v2.txt"
    assert doc.status == "processing"
    assert doc.summary is None
    assert doc.tags == []
