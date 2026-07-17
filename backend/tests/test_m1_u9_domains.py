"""M1-U9：域名白名单管理端点（管理员维护）。"""

import uuid

import pytest

pytestmark = pytest.mark.asyncio


async def test_admin_add_list_delete_domain(client, seed_user):
    _, admin = await seed_user("admin")

    # 新增
    add = await client.post(
        "/auth/allowed-domains", json={"domain": "partner-a.com"}, headers=admin
    )
    assert add.status_code == 201
    domain_id = add.json()["id"]
    assert add.json()["domain"] == "partner-a.com"

    # 列表
    lst = await client.get("/auth/allowed-domains", headers=admin)
    assert lst.status_code == 200
    assert any(d["domain"] == "partner-a.com" for d in lst.json())

    # 删除
    dele = await client.delete(f"/auth/allowed-domains/{domain_id}", headers=admin)
    assert dele.status_code == 204
    lst2 = await client.get("/auth/allowed-domains", headers=admin)
    assert all(d["domain"] != "partner-a.com" for d in lst2.json())


async def test_non_admin_cannot_manage_domains(client, seed_user):
    _, internal = await seed_user("user")
    assert (await client.get("/auth/allowed-domains", headers=internal)).status_code == 403
    assert (
        await client.post(
            "/auth/allowed-domains", json={"domain": "x.com"}, headers=internal
        )
    ).status_code == 403


async def test_add_domain_requires_auth(client):
    resp = await client.post("/auth/allowed-domains", json={"domain": "x.com"})
    assert resp.status_code == 401


async def test_delete_unknown_domain_404(client, seed_user):
    _, admin = await seed_user("admin")
    resp = await client.delete(f"/auth/allowed-domains/{uuid.uuid4()}", headers=admin)
    assert resp.status_code == 404


async def test_add_domain_idempotent(client, seed_user):
    _, admin = await seed_user("admin")
    first = await client.post(
        "/auth/allowed-domains", json={"domain": "dup.com"}, headers=admin
    )
    second = await client.post(
        "/auth/allowed-domains", json={"domain": "dup.com"}, headers=admin
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_end_to_end_admin_enables_registration(client, seed_user):
    """管理员添加域名后，该域名用户才能注册（空=全拒绝的闭环）。"""
    # 先证明拒绝
    before = await client.post(
        "/auth/register",
        json={"email": "u@enabled.com", "password": "longenough1"},
    )
    assert before.status_code == 403

    # 管理员加域名
    _, admin = await seed_user("admin")
    await client.post(
        "/auth/allowed-domains", json={"domain": "enabled.com"}, headers=admin
    )

    # 现在可注册
    after = await client.post(
        "/auth/register",
        json={"email": "u@enabled.com", "password": "longenough1"},
    )
    assert after.status_code == 201
