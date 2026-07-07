"""M2-U3：本地存储封装 —— key 生成、读写、路径穿越防护。"""

import uuid

import pytest

from app.storage.base import generate_storage_key, get_storage
from app.storage.local import StorageError


def test_generate_key_decoupled_from_filename():
    ws = uuid.uuid4()
    key = generate_storage_key(ws)
    # key 以 workspace 为前缀、不含客户端文件名
    assert key.startswith(f"{ws}/")
    assert ".." not in key
    assert "/" == key[len(str(ws))]


@pytest.mark.asyncio
async def test_save_and_read_roundtrip():
    storage = get_storage()
    key = generate_storage_key(uuid.uuid4())
    await storage.save(key, b"file-content")
    assert await storage.read_bytes(key) == b"file-content"


@pytest.mark.asyncio
async def test_read_missing_raises():
    storage = get_storage()
    with pytest.raises(StorageError):
        await storage.read_bytes(generate_storage_key(uuid.uuid4()))


@pytest.mark.asyncio
async def test_path_traversal_rejected_on_save():
    storage = get_storage()
    with pytest.raises(StorageError):
        await storage.save("../../etc/passwd", b"x")


@pytest.mark.asyncio
async def test_path_traversal_rejected_on_read():
    storage = get_storage()
    with pytest.raises(StorageError):
        await storage.read_bytes("../../../etc/passwd")


@pytest.mark.asyncio
async def test_download_url_validates_key():
    storage = get_storage()
    key = generate_storage_key(uuid.uuid4())
    url = await storage.download_url(key, expires_in=300)
    assert key in url
