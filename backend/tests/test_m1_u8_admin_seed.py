"""M1-U8：管理员种子 + 改密。"""

import pytest

from app.services import user_service
from app.services.user_service import (
    get_user_by_email,
    seed_admin,
)

pytestmark = pytest.mark.asyncio


async def test_seed_admin_creates_admin(db_session, monkeypatch):
    settings = user_service.get_settings()
    monkeypatch.setattr(settings, "admin_email", "boss@company.com")
    monkeypatch.setattr(settings, "admin_password", "StrongPass123")

    admin = await seed_admin(db_session)
    assert admin is not None
    assert admin.role == "admin"
    assert admin.email == "boss@company.com"
    # 密码 bcrypt 存库，不是明文
    assert admin.password_hash != "StrongPass123"


async def test_seed_admin_is_idempotent(db_session, monkeypatch):
    settings = user_service.get_settings()
    monkeypatch.setattr(settings, "admin_email", "boss@company.com")
    monkeypatch.setattr(settings, "admin_password", "StrongPass123")

    first = await seed_admin(db_session)
    original_hash = first.password_hash
    # 再次种子：不新建、不覆盖密码
    again = await seed_admin(db_session)
    assert again.id == first.id
    assert again.password_hash == original_hash


async def test_seed_admin_skipped_when_unset(db_session, monkeypatch):
    settings = user_service.get_settings()
    monkeypatch.setattr(settings, "admin_email", "")
    monkeypatch.setattr(settings, "admin_password", "")
    assert await seed_admin(db_session) is None


async def test_change_password_flow(client, seed_user):
    # 用 seed_user 造一个用户并拿 token，但 seed_user 用固定密码 longenough1
    _, headers = await seed_user("user")
    # 错误当前密码 -> 400
    bad = await client.post(
        "/auth/change-password",
        json={"current_password": "wrongpass", "new_password": "newpass123"},
        headers=headers,
    )
    assert bad.status_code == 400

    # 正确当前密码 -> 204
    ok = await client.post(
        "/auth/change-password",
        json={"current_password": "longenough1", "new_password": "newpass123"},
        headers=headers,
    )
    assert ok.status_code == 204


async def test_change_password_requires_auth(client):
    resp = await client.post(
        "/auth/change-password",
        json={"current_password": "x", "new_password": "newpass123"},
    )
    assert resp.status_code == 401


async def test_admin_can_login_after_seed(client, db_session, monkeypatch):
    """种子后的 admin 能用配置的密码登录。"""
    settings = user_service.get_settings()
    monkeypatch.setattr(settings, "admin_email", "root@company.com")
    monkeypatch.setattr(settings, "admin_password", "RootPass123")
    await seed_admin(db_session)
    assert await get_user_by_email(db_session, "root@company.com") is not None

    resp = await client.post(
        "/auth/login",
        json={"email": "root@company.com", "password": "RootPass123"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"
