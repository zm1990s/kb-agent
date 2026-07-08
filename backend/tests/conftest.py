"""测试夹具：在导入应用前注入最小必需的环境变量，并提供 DB / HTTP client。"""

import os
import tempfile

# 在任何 app.* 导入之前设置环境变量（config 用 lru_cache 读取）
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://kbagent:kbagent@localhost/kbagent")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-prod")
os.environ.setdefault("LOCAL_STORAGE_DIR", tempfile.mkdtemp(prefix="kb_test_store_"))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


def _db_available() -> bool:
    return "@postgres" in os.environ["DATABASE_URL"] or "@localhost" in os.environ["DATABASE_URL"]


@pytest_asyncio.fixture
async def db_engine():
    """为每个用到 DB 的测试建表、结束后清理（独立 schema，隔离测试）。"""
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.db import Base
    from app.models import auth as _auth  # noqa: F401  # 注册模型到 metadata
    from app.models import chat as _chat  # noqa: F401  # 注册模型到 metadata
    from app.models import document as _document  # noqa: F401  # 注册模型到 metadata
    from app.models import rbac as _rbac  # noqa: F401  # 注册模型到 metadata
    from app.models import settings as _settings  # noqa: F401  # 注册模型到 metadata

    engine = create_async_engine(os.environ["DATABASE_URL"])
    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"无可用数据库，跳过 DB 测试: {exc}")

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_engine):
    """基于建好表的 DB 的 httpx 异步客户端。

    覆盖 get_session 依赖，让应用与测试共用同一 engine（同一事件循环），
    避免模块级 engine 在多测试事件循环间复用 asyncpg 连接导致的错误。
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.db import get_session
    from app.main import app

    test_sessionmaker = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def _override_get_session():
        async with test_sessionmaker() as session:
            yield session

    # 端点触发的后台归类 worker 在 HTTP 测试中改为 no-op：
    # worker 逻辑已在 test_m2_u5_classify 直接覆盖，此处避免 fire-and-forget
    # 任务与测试 teardown 竞争产生噪声。
    import app.api.documents as _documents_api

    def _noop_enqueue(_task_id):
        return None

    _orig_enqueue = _documents_api.enqueue_classification
    _documents_api.enqueue_classification = _noop_enqueue

    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    _documents_api.enqueue_classification = _orig_enqueue


@pytest_asyncio.fixture
async def db_session(db_engine):
    """产出一个绑定到测试 engine 的 async 会话（供直接调用 service/deps 使用）。"""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def seed_domain(db_engine):
    """向 DB 白名单插入域名的工厂（注册测试需要）。"""
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.models.auth import AllowedDomain

    maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _add(domain: str = "company.com"):
        async with maker() as session:
            session.add(AllowedDomain(id=uuid.uuid4(), domain=domain.lower()))
            await session.commit()

    return _add


@pytest_asyncio.fixture
async def seed_user(db_engine):
    """直接向 DB 插入指定角色用户，返回 (user_id, auth_headers) 的工厂。

    用于需要 admin / partner 等非 internal 角色的测试（注册端点只产 internal）。
    """
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.core.security import create_access_token, hash_password
    from app.models.auth import User

    maker = async_sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)

    async def _make(role: str = "internal", email: str | None = None):
        uid = uuid.uuid4()
        email = email or f"{role}-{uid.hex[:8]}@company.com"
        async with maker() as session:
            session.add(
                User(id=uid, email=email, password_hash=hash_password("longenough1"), role=role)
            )
            await session.commit()
        token = create_access_token(user_id=uid, role=role)
        return uid, {"Authorization": f"Bearer {token}"}

    return _make
