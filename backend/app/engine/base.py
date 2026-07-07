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


def get_engine() -> EngineProtocol:
    """引擎工厂：按 ENGINE_BACKEND 选择实现。"""
    settings = get_settings()
    backend = settings.engine_backend.lower()

    if backend == "claude_cli":
        from app.engine.claude_cli import ClaudeCliEngine

        return ClaudeCliEngine()

    # 预留：openclaw / codex 等未来后端
    raise NotImplementedError(f"未实现的引擎后端: {settings.engine_backend!r}")
