"""M1-U4：登录 + /auth/me。"""

import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, email="user@company.com", password="longenough1"):
    return await client.post(
        "/auth/register", json={"email": email, "password": password}
    )


async def test_login_correct_credentials_returns_jwt(client):
    await _register(client)
    resp = await client.post(
        "/auth/login",
        json={"email": "user@company.com", "password": "longenough1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["role"] == "internal"


async def test_login_wrong_password_returns_401(client):
    await _register(client)
    resp = await client.post(
        "/auth/login",
        json={"email": "user@company.com", "password": "wrong-password"},
    )
    assert resp.status_code == 401


async def test_login_unknown_email_returns_401(client):
    resp = await client.post(
        "/auth/login",
        json={"email": "ghost@company.com", "password": "longenough1"},
    )
    assert resp.status_code == 401


async def test_me_with_token_returns_user(client):
    await _register(client)
    login = await client.post(
        "/auth/login",
        json={"email": "user@company.com", "password": "longenough1"},
    )
    token = login.json()["access_token"]
    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "user@company.com"
    assert "password_hash" not in body


async def test_me_without_token_returns_401(client):
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_me_with_invalid_token_returns_401(client):
    resp = await client.get(
        "/auth/me", headers={"Authorization": "Bearer not.a.valid.token"}
    )
    assert resp.status_code == 401
