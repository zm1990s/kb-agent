"""M0 冒烟测试：健康检查、引擎/存储工厂、路径穿越防护。"""

import uuid

import pytest
from fastapi.testclient import TestClient

from app.engine.base import EngineProtocol, get_engine
from app.main import app
from app.storage.base import StorageProtocol, get_storage
from app.storage.local import StorageError

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_engine_factory_returns_protocol():
    engine = get_engine()
    assert isinstance(engine, EngineProtocol)


def test_storage_factory_returns_protocol():
    storage = get_storage()
    assert isinstance(storage, StorageProtocol)


@pytest.mark.asyncio
async def test_local_storage_roundtrip():
    storage = get_storage()
    key = f"{uuid.uuid4()}/{uuid.uuid4()}.txt"
    await storage.save(key, b"hello")
    path = await storage.open_path(key)
    assert path.read_bytes() == b"hello"


@pytest.mark.asyncio
async def test_local_storage_rejects_path_traversal():
    storage = get_storage()
    with pytest.raises(StorageError):
        await storage.save("../../etc/evil.txt", b"pwned")
