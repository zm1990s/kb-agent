"""MF-U7：引擎配置端点（管理员）。"""

import pytest

pytestmark = pytest.mark.asyncio


async def test_get_engine_config_lists_catalog(client, seed_user):
    _, admin = await seed_user("admin")
    resp = await client.get("/settings/engine", headers=admin)
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"] == "claude_cli"  # 默认
    ids = {o["id"]: o for o in body["options"]}
    assert ids["claude_cli"]["available"] is True
    assert ids["codex"]["available"] is False
    assert ids["openclaw"]["available"] is False


async def test_set_engine_available_ok(client, seed_user):
    _, admin = await seed_user("admin")
    resp = await client.put(
        "/settings/engine", json={"backend": "claude_cli"}, headers=admin
    )
    assert resp.status_code == 200
    assert resp.json()["current"] == "claude_cli"


async def test_set_engine_unavailable_400(client, seed_user):
    _, admin = await seed_user("admin")
    for bad in ("codex", "openclaw", "nonsense"):
        resp = await client.put(
            "/settings/engine", json={"backend": bad}, headers=admin
        )
        assert resp.status_code == 400, bad


async def test_engine_config_admin_only(client, seed_user):
    _, internal = await seed_user("user")
    assert (await client.get("/settings/engine", headers=internal)).status_code == 403
    assert (
        await client.put(
            "/settings/engine", json={"backend": "claude_cli"}, headers=internal
        )
    ).status_code == 403


async def test_engine_config_requires_auth(client):
    assert (await client.get("/settings/engine")).status_code == 401


async def test_engine_selection_persists(client, seed_user, db_session):
    """选择写入 DB，后端解析生效。"""
    from app.services.settings_service import get_engine_backend

    _, admin = await seed_user("admin")
    await client.put("/settings/engine", json={"backend": "claude_cli"}, headers=admin)
    # 直接从 DB 读，确认持久化
    assert await get_engine_backend(db_session) == "claude_cli"
