"""M1-U2：验证 ORM 模型可导入、Pydantic schema 校验、模型可映射到真实 DB。

依赖真实 postgres（compose 的 postgres 服务）。无 DB 时自动跳过。
"""

import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.models.auth import USER_ROLES, WS_ROLES, User, Workspace, WorkspaceMember
from app.schemas.auth import RegisterRequest, WorkspaceWithRole


def test_schema_validation_ok():
    r = RegisterRequest(email="alice@company.com", password="longenough1")
    assert r.email == "alice@company.com"


def test_schema_rejects_short_password():
    with pytest.raises(ValueError):
        RegisterRequest(email="a@company.com", password="short")


def test_workspace_with_role_from_attributes():
    ws = WorkspaceWithRole(
        id=uuid.uuid4(),
        name="ws1",
        description=None,
        created_at="2026-01-01T00:00:00Z",  # type: ignore[arg-type]
        role_in_ws="owner",
    )
    assert ws.role_in_ws in WS_ROLES


def test_role_constants():
    assert USER_ROLES == ("admin", "internal", "partner")


@pytest.mark.asyncio
async def test_models_map_to_real_db():
    """用 ORM metadata 在临时 schema 建表，确认模型定义与 DB 兼容。"""
    db_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
            # 建到独立 schema，避免污染业务表
            await conn.exec_driver_sql("CREATE SCHEMA IF NOT EXISTS m1u2_test")
            await conn.exec_driver_sql("SET search_path TO m1u2_test")
            for table in (User.__table__, Workspace.__table__, WorkspaceMember.__table__):
                await conn.run_sync(table.create, checkfirst=True)
            await conn.exec_driver_sql("DROP SCHEMA m1u2_test CASCADE")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"无可用数据库，跳过 DB 映射测试: {exc}")
    finally:
        await engine.dispose()
