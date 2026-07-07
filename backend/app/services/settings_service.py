"""应用设置业务逻辑。当前用于引擎（LLM 后端）选择。

引擎目录：Claude CLI 已实现；Codex / OpenClaw 预留占位（未实现，前端灰显）。
选择持久化在 app_settings，重启仍生效。
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.settings import AppSetting

ENGINE_KEY = "engine_backend"


@dataclass(frozen=True)
class EngineOption:
    id: str
    label: str
    available: bool


# 引擎目录：唯一真相源，前端据此渲染（未实现的置灰）。
ENGINE_CATALOG: list[EngineOption] = [
    EngineOption(id="claude_cli", label="Claude CLI", available=True),
    EngineOption(id="codex", label="Codex（未实现）", available=False),
    EngineOption(id="openclaw", label="OpenClaw（未实现）", available=False),
]

_AVAILABLE_IDS = {e.id for e in ENGINE_CATALOG if e.available}


class EngineNotAvailableError(Exception):
    """选择了未实现/未知的引擎。"""


async def get_setting(session: AsyncSession, key: str) -> str | None:
    result = await session.execute(select(AppSetting.value).where(AppSetting.key == key))
    return result.scalar_one_or_none()


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    row = await session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value=value))
    else:
        row.value = value
    await session.commit()


async def get_engine_backend(session: AsyncSession) -> str:
    """当前生效的引擎后端：DB 设置优先，回退到配置默认。"""
    stored = await get_setting(session, ENGINE_KEY)
    return stored or get_settings().engine_backend


async def set_engine_backend(session: AsyncSession, backend: str) -> None:
    """设置引擎后端；仅允许 available 的引擎。"""
    if backend not in _AVAILABLE_IDS:
        raise EngineNotAvailableError(backend)
    await set_setting(session, ENGINE_KEY, backend)
