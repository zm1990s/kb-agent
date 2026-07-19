"""LocalStorage —— MVP 本地文件系统实现。

安全要点（SECURITY #5 防路径穿越）：
- 拼路径后用 realpath 规范化，断言结果仍在 LOCAL_STORAGE_DIR 之内，越界一律拒绝。
- 调用方传入的 key 由服务端生成（UUID），不应含客户端文件名；此处仍做防御式校验。
"""

from pathlib import Path

from app.core.config import get_settings


class StorageError(RuntimeError):
    """存储操作失败。"""


class LocalStorage:
    """把原始文件存到 LOCAL_STORAGE_DIR 下的本地实现。"""

    def __init__(self) -> None:
        settings = get_settings()
        self._root = Path(settings.local_storage_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve_within_root(self, key: str) -> Path:
        """把 key 解析为绝对路径，并确保它落在存储根目录内。"""
        candidate = (self._root / key).resolve()
        # 关键校验：规范化后的路径必须在根目录之下
        if self._root != candidate and self._root not in candidate.parents:
            raise StorageError(f"非法存储 key，越出存储根目录: {key!r}")
        return candidate

    async def save(self, key: str, data: bytes) -> str:
        path = self._resolve_within_root(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    async def open_path(self, key: str) -> Path:
        path = self._resolve_within_root(key)
        if not path.is_file():
            raise StorageError(f"文件不存在: {key!r}")
        return path

    async def read_bytes(self, key: str) -> bytes:
        path = await self.open_path(key)
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._resolve_within_root(key)
        if not path.is_file():
            raise FileNotFoundError(key)
        path.unlink()

    async def download_url(self, key: str, expires_in: int) -> str:
        # 本地实现：下载走后端受控端点 /documents/{id}/download，
        # 该端点用 JWT + require_ws_member 鉴权（见 M2-U7）。此处仅校验 key 合法。
        self._resolve_within_root(key)
        return f"/documents/download?key={key}"

    async def resolve_dir(self, key_prefix: str) -> Path:
        """把 key 前缀解析为真实目录（创建后返回），供 CLI 在其中读写。"""
        path = self._resolve_within_root(key_prefix)
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def delete_dir(self, key_prefix: str) -> None:
        """递归删除目录；不存在则静默。"""
        import shutil

        path = self._resolve_within_root(key_prefix)
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)

    async def stat_files(self, key_prefix: str) -> list[dict]:
        """列出目录下文件及 mtime/size；目录不存在返回空列表。"""
        path = self._resolve_within_root(key_prefix)
        if not path.is_dir():
            return []
        out: list[dict] = []
        for entry in path.iterdir():
            if entry.is_file():
                st = entry.stat()
                out.append({
                    "key": f"{key_prefix}/{entry.name}",
                    "mtime": st.st_mtime,
                    "size": st.st_size,
                })
        return out
