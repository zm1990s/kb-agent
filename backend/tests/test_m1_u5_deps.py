"""M1-U5：require_admin / require_auth 鉴权依赖。"""

import uuid

import pytest
from fastapi import HTTPException

from app.core.deps import require_admin
from app.models.auth import User

pytestmark = pytest.mark.asyncio


def _user(role: str) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{role}@company.com",
        password_hash="x",
        role=role,
    )


async def test_require_admin_allows_admin():
    admin = _user("admin")
    result = await require_admin(current_user=admin)
    assert result is admin


async def test_require_admin_rejects_internal():
    with pytest.raises(HTTPException) as exc:
        await require_admin(current_user=_user("internal"))
    assert exc.value.status_code == 403


async def test_require_admin_rejects_partner():
    with pytest.raises(HTTPException) as exc:
        await require_admin(current_user=_user("partner"))
    assert exc.value.status_code == 403
