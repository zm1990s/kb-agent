"""Agent 引擎抽象层 —— 全项目唯一的 LLM 出口。

业务层只依赖 EngineProtocol，不感知底层是 Claude CLI / OpenClaw / Codex。
通过 ENGINE_BACKEND 配置切换实现。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.config import get_settings


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

    # 预留：openclaw / codex 等未来后端
    raise NotImplementedError(f"未实现的引擎后端: {resolved!r}")
