"""M1-U3b：注册 + 域名白名单（DB 维护）。覆盖三种情况 + 白名单绕过防护。"""

import pytest

from app.services.user_service import is_domain_allowed

pytestmark = pytest.mark.asyncio


# ── 白名单匹配（DB）──────────────────────────────────────


async def test_whitelist_empty_rejects_all(db_session):
    """空白名单 = 全拒绝（安全默认）。"""
    assert await is_domain_allowed(db_session, "alice@company.com") is False


async def test_whitelist_exact_match(db_session, seed_domain):
    await seed_domain("company.com")
    assert await is_domain_allowed(db_session, "alice@company.com") is True


async def test_whitelist_rejects_suffix_lookalike(db_session, seed_domain):
    """SECURITY #9：完整域名相等匹配，fakecompany.com 不应被放行。"""
    await seed_domain("company.com")
    assert await is_domain_allowed(db_session, "evil@fakecompany.com") is False
    assert await is_domain_allowed(db_session, "evil@company.com.evil.com") is False


async def test_whitelist_case_insensitive(db_session, seed_domain):
    await seed_domain("company.com")
    assert await is_domain_allowed(db_session, "Alice@Company.COM") is True


# ── 注册端点（依赖 DB）──────────────────────────────────


async def test_register_allowed_domain_returns_201(client, seed_domain):
    await seed_domain("company.com")
    resp = await client.post(
        "/auth/register",
        json={"email": "newuser@company.com", "password": "longenough1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "newuser@company.com"
    assert "password_hash" not in body


async def test_register_disallowed_domain_returns_403(client, seed_domain):
    await seed_domain("company.com")
    resp = await client.post(
        "/auth/register",
        json={"email": "outsider@fakecompany.com", "password": "longenough1"},
    )
    assert resp.status_code == 403


async def test_register_empty_whitelist_returns_403(client):
    """未配置任何域名时，注册全拒绝。"""
    resp = await client.post(
        "/auth/register",
        json={"email": "anyone@company.com", "password": "longenough1"},
    )
    assert resp.status_code == 403


async def test_register_duplicate_returns_409(client, seed_domain):
    await seed_domain("company.com")
    payload = {"email": "dup@company.com", "password": "longenough1"}
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409


async def test_register_invalid_email_returns_422(client, seed_domain):
    await seed_domain("company.com")
    resp = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "longenough1"},
    )
    assert resp.status_code == 422
