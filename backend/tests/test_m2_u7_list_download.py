"""M2-U7：文档列表/详情/下载，含隔离与下载安全头。"""

import io

import pytest

pytestmark = pytest.mark.asyncio


async def _ws(client, headers, name="ws"):
    r = await client.post("/workspaces", json={"name": name}, headers=headers)
    return r.json()["id"]


async def _upload(client, headers, ws_id, content=b"hello", name="a.txt"):
    r = await client.post(
        f"/workspaces/{ws_id}/documents",
        files={"file": (name, io.BytesIO(content), "text/plain")},
        headers=headers,
    )
    return r.json()["id"]


async def test_list_documents(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    await _upload(client, admin, ws_id)
    resp = await client.get(f"/workspaces/{ws_id}/documents", headers=admin)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["title"] == "a.txt"
    assert body[0]["status"] == "processing"


async def test_list_isolation_cross_workspace(client, seed_user):
    """A 空间的文档不出现在 B 空间列表；非成员访问 A 列表 403。"""
    _, admin = await seed_user("admin")
    ws_a = await _ws(client, admin, "A")
    await _upload(client, admin, ws_a)

    _, partner = await seed_user("partner")
    resp = await client.get(f"/workspaces/{ws_a}/documents", headers=partner)
    assert resp.status_code == 403  # 非成员


async def test_document_detail(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    doc_id = await _upload(client, admin, ws_id)
    resp = await client.get(f"/documents/{doc_id}", headers=admin)
    assert resp.status_code == 200
    assert resp.json()["id"] == doc_id


async def test_detail_non_member_404(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    doc_id = await _upload(client, admin, ws_id)
    _, other = await seed_user("internal")
    resp = await client.get(f"/documents/{doc_id}", headers=other)
    assert resp.status_code == 404


async def test_download_returns_file_with_safe_headers(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    doc_id = await _upload(client, admin, ws_id, content=b"secret-bytes", name="s.txt")
    resp = await client.get(f"/documents/{doc_id}/download", headers=admin)
    assert resp.status_code == 200
    assert resp.content == b"secret-bytes"
    # SECURITY #5：强制 attachment + nosniff
    assert resp.headers["content-disposition"].startswith("attachment")
    assert resp.headers["x-content-type-options"] == "nosniff"


async def test_download_non_member_404(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    doc_id = await _upload(client, admin, ws_id)
    _, other = await seed_user("partner")
    resp = await client.get(f"/documents/{doc_id}/download", headers=other)
    assert resp.status_code == 404


async def test_download_requires_auth(client, seed_user):
    _, admin = await seed_user("admin")
    ws_id = await _ws(client, admin)
    doc_id = await _upload(client, admin, ws_id)
    resp = await client.get(f"/documents/{doc_id}/download")
    assert resp.status_code == 401
