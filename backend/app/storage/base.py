"""存储抽象层 —— 全项目唯一的文件存取出口。

业务层只依赖 StorageProtocol，不直接拼路径读写文件（防路径穿越，见 SECURITY #5）。
MVP 用 LocalStorage（本地文件系统），未来可换 S3/OSS 而不动业务层。
"""

import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import get_settings


def generate_storage_key(workspace_id: uuid.UUID) -> str:
    """服务端生成 storage_key，与客户端文件名解耦（SECURITY #5 防路径穿越）。

    形如 ``{workspace_id}/{uuid4}``，不含任何用户可控的路径片段。
    """
    return f"{workspace_id}/{uuid.uuid4().hex}"


@runtime_checkable
class StorageProtocol(Protocol):
    """所有存储实现遵守的接口。"""

    async def save(self, key: str, data: bytes) -> str:
        """保存字节内容，返回可用于后续存取的 storage_key。"""
        ...

    async def open_path(self, key: str) -> Path:
        """返回本地可读路径（供 CLI 读原文）。"""
        ...

    async def read_bytes(self, key: str) -> bytes:
        """读取文件字节内容（供下载端点）。"""
        ...

    async def delete(self, key: str) -> None:
        """删除文件；不存在时抛 FileNotFoundError。"""
        ...

    async def download_url(self, key: str, expires_in: int) -> str:
        """返回限时下载 URL（本地实现指向受控下载端点）。"""
        ...


def get_storage() -> StorageProtocol:
    """存储工厂：按 STORAGE_BACKEND 选择实现。"""
    settings = get_settings()
    backend = settings.storage_backend.lower()

    if backend == "local":
        from app.storage.local import LocalStorage

        return LocalStorage()

    # 预留：s3 / oss 等未来后端
    raise NotImplementedError(f"未实现的存储后端: {settings.storage_backend!r}")
