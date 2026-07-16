"""Agent 引擎抽象层 —— 全项目唯一的 LLM 出口。

业务层只依赖 EngineProtocol，不感知底层是 Claude CLI / OpenClaw / Codex。
通过 ENGINE_BACKEND 配置切换实现。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import get_settings


class EngineError(RuntimeError):
    """引擎调用失败（所有引擎实现的公共基类）。"""


@dataclass
class EngineResult:
    """引擎调用的统一返回。"""

    text: str
    raw: dict = field(default_factory=dict)


@runtime_checkable
class EngineProtocol(Protocol):
    """所有引擎实现遵守的接口。"""

    async def complete(
        self,
        prompt: str,
        *,
        files: list[Path] | None = None,
        system: str | None = None,
    ) -> EngineResult:
        """给定 prompt（可附带文件），返回模型输出。"""
        ...


def get_engine(backend: str | None = None, model: str | None = None) -> EngineProtocol:
    """引擎工厂：按给定 backend（或配置默认）选择实现。

    backend 通常由 settings_service.get_engine_backend() 从 DB 解析后传入，
    以尊重管理员在应用内的选择；不传则回退到 ENGINE_BACKEND 配置。
    model 为可选的模型覆盖，优先级高于环境变量 CLAUDE_MODEL。
    """
    resolved = (backend or get_settings().engine_backend).lower()

    if resolved == "claude_cli":
        from app.engine.claude_cli import ClaudeCliEngine

        return ClaudeCliEngine(model=model)

    if resolved == "openai_compat":
        raise NotImplementedError(
            "openai_compat 引擎须通过 get_chat_engine() 获取（需要 DB session）"
        )

    # 预留：openclaw / codex 等未来后端
    raise NotImplementedError(f"未实现的引擎后端: {resolved!r}")


async def get_chat_engine(session) -> "EngineProtocol":
    """对话引擎工厂：读 chat_engine_backend 配置，返回相应引擎实例。

    文档归类请直接用 get_engine("claude_cli", model=...)，不要用此函数。
    """
    from app.services.settings_service import (
        MODEL_CHAT_KEY,
        get_chat_engine_backend,
        get_openai_api_key,
        get_openai_base_url,
        get_openai_model,
        get_task_model,
    )

    backend = await get_chat_engine_backend(session)
    if backend == "openai_compat":
        from app.engine.openai_compat import OpenAICompatEngine

        base_url = await get_openai_base_url(session)
        api_key = await get_openai_api_key(session)
        model = await get_openai_model(session)
        return OpenAICompatEngine(base_url=base_url, api_key=api_key or "none", model=model)

    # 默认 claude_cli
    model = await get_task_model(session, MODEL_CHAT_KEY)
    return get_engine("claude_cli", model=model)
