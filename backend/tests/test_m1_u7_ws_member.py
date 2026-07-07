"""M1-U7：require_ws_member 依赖 + M1 集成全链路。"""

import uuid

import pytest
from fastapi import HTTPException

from app.core.deps import require_ws_member
from app.models.auth import User, Workspace, WorkspaceMember

pytestmark = pytest.mark.asyncio


async def _mk_user(session, role="internal") -> User:
    u = User(
        id=uuid.uuid4(),
        email=f"{role}-{uuid.uuid4().hex[:8]}@company.com",
        password_hash="x",
        role=role,
    )
    session.add(u)
    await session.commit()
    return u


async def _mk_ws(session, name="ws") -> Workspace:
    ws = Workspace(id=uuid.uuid4(), name=name)
    session.add(ws)
    await session.commit()
    return ws


async def test_require_ws_member_allows_member(db_session):
    user = await _mk_user(db_session)
    ws = await _mk_ws(db_session)
    db_session.add(
        WorkspaceMember(workspace_id=ws.id, user_id=user.id, role_in_ws="viewer")
    )
    await db_session.commit()

    result = await require_ws_member(
        workspace_id=ws.id, current_user=user, session=db_session
    )
    assert result is user


async def test_require_ws_member_rejects_non_member(db_session):
    user = await _mk_user(db_session)
    ws = await _mk_ws(db_session)  # 未加入
    with pytest.raises(HTTPException) as exc:
        await require_ws_member(
            workspace_id=ws.id, current_user=user, session=db_session
        )
    assert exc.value.status_code == 403


async def test_require_ws_member_admin_not_auto_member(db_session):
    """管理员不自动拥有所有空间访问权——未加入仍 403。"""
    admin = await _mk_user(db_session, role="admin")
    ws = await _mk_ws(db_session)
    with pytest.raises(HTTPException) as exc:
        await require_ws_member(
            workspace_id=ws.id, current_user=admin, session=db_session
        )
    assert exc.value.status_code == 403


# ── M1 集成：注册→登录→建空间→加成员→列表 全链路 ──────────


async def test_m1_end_to_end(client, seed_user, seed_domain):
    await seed_domain("company.com")
    # 管理员建空间
    admin_id, admin_headers = await seed_user("admin")
    ws = await client.post(
        "/workspaces", json={"name": "集成空间"}, headers=admin_headers
    )
    assert ws.status_code == 201
    ws_id = ws.json()["id"]

    # 新员工注册 → 登录
    reg = await client.post(
        "/auth/register",
        json={"email": "newbie@company.com", "password": "longenough1"},
    )
    assert reg.status_code == 201
    new_user_id = reg.json()["id"]

    login = await client.post(
        "/auth/login",
        json={"email": "newbie@company.com", "password": "longenough1"},
    )
    assert login.status_code == 200
    new_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    # 加入前：/auth/me 正常，但看不到空间
    me = await client.get("/auth/me", headers=new_headers)
    assert me.status_code == 200
    assert await client.get("/workspaces", headers=new_headers) is not None
    before = await client.get("/workspaces", headers=new_headers)
    assert before.json() == []

    # 管理员加成员
    add = await client.post(
        f"/workspaces/{ws_id}/members",
        json={"user_id": new_user_id, "role_in_ws": "editor"},
        headers=admin_headers,
    )
    assert add.status_code == 201

    # 加入后：能看到该空间
    after = await client.get("/workspaces", headers=new_headers)
    body = after.json()
    assert len(body) == 1
    assert body[0]["id"] == ws_id
    assert body[0]["role_in_ws"] == "editor"
