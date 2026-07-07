"""M1-U3b：注册 + 域名白名单。覆盖三种情况 + 白名单绕过防护。"""

import pytest

from app.services.user_service import is_domain_allowed

# ── 白名单匹配单测（不依赖 DB）──────────────────────────


def test_whitelist_exact_match():
    # conftest 设 ALLOWED_EMAIL_DOMAINS=company.com
    assert is_domain_allowed("alice@company.com") is True


def test_whitelist_rejects_suffix_lookalike():
    """SECURITY #9：完整域名相等匹配，fakecompany.com 不应被放行。"""
    assert is_domain_allowed("evil@fakecompany.com") is False
    assert is_domain_allowed("evil@company.com.evil.com") is False


def test_whitelist_case_insensitive():
    assert is_domain_allowed("Alice@Company.COM") is True


# ── 注册端点（依赖 DB）──────────────────────────────────


@pytest.mark.asyncio
async def test_register_allowed_domain_returns_201(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "newuser@company.com", "password": "longenough1"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "newuser@company.com"
    assert "id" in body
    assert "password_hash" not in body  # 不泄漏哈希


@pytest.mark.asyncio
async def test_register_disallowed_domain_returns_403(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "outsider@fakecompany.com", "password": "longenough1"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_register_duplicate_returns_409(client):
    payload = {"email": "dup@company.com", "password": "longenough1"}
    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201
    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "longenough1"},
    )
    assert resp.status_code == 422
