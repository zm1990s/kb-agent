"""Agent 引擎抽象层 —— 全项目唯一的 LLM 出口。

业务层只依赖 EngineProtocol，不感知底层是 Claude CLI / OpenClaw / Codex。
通过 ENGINE_BACKEND 配置切换实现。
"""

from collections.abc import AsyncGenerator
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


@dataclass
class ThinkingChunk:
    """流式 thinking 增量（仅 thinking 模型产出）。"""

    text: str


@dataclass
class TextChunk:
    """流式文本增量。"""

    text: str


@runtime_checkable
class EngineProtocol(Protocol):
    """所有引擎实现遵守的接口。"""

    async def complete(
        self,
        prompt: str,
        *,
        files: list[Path] | None = None,
        system: str | None = None,
        cwd: Path | None = None,
    ) -> EngineResult:
        """给定 prompt（可附带文件），返回模型输出。

        cwd 为可选的工作目录：支持文件工具的引擎（如 Claude CLI）会在此目录下
        运行子进程，Agent 创建的文件落在这里；不支持的引擎应忽略该参数。
        """
        ...

    async def complete_streaming(
        self,
        prompt: str,
        *,
        files: list[Path] | None = None,
        system: str | None = None,
        cwd: Path | None = None,
    ) -> AsyncGenerator["ThinkingChunk | TextChunk", None]:
        """流式调用：逐块 yield ThinkingChunk 或 TextChunk。
        不支持的引擎可以不实现此方法（用 hasattr 判断）。cwd 语义同 complete。
        """
        ...


def get_engine(
    backend: str | None = None,
    model: str | None = None,
    audit_user: str | None = None,
) -> EngineProtocol:
    """引擎工厂：按给定 backend（或配置默认）选择实现。

    backend 通常由 settings_service.get_engine_backend() 从 DB 解析后传入，
    以尊重管理员在应用内的选择；不传则回退到 ENGINE_BACKEND 配置。
    model 为可选的模型覆盖，优先级高于环境变量 CLAUDE_MODEL。
    audit_user 为发起调用的用户标识，写入 CLI hook 安全审计（仅 claude_cli 生效）。
    """
    resolved = (backend or get_settings().engine_backend).lower()

    if resolved == "claude_cli":
        from app.engine.claude_cli import ClaudeCliEngine

        return ClaudeCliEngine(model=model, audit_user=audit_user)

    if resolved == "openai_compat":
        raise NotImplementedError(
            "openai_compat 引擎须通过 get_chat_engine() 获取（需要 DB session）"
        )

    # 预留：openclaw / codex 等未来后端
    raise NotImplementedError(f"未实现的引擎后端: {resolved!r}")


async def get_chat_engine(
    session,
    *,
    extra_headers: dict[str, str] | None = None,
    model_key: str | None = None,
) -> "EngineProtocol":
    """对话引擎工厂：读 chat_engine_backend 配置，返回相应引擎实例。

    extra_headers 仅对 OpenAICompatEngine 生效（ClaudeCliEngine 静默忽略）。
    model_key 指定从 app_settings 读取模型的 key，默认 MODEL_CHAT_KEY。
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
        return OpenAICompatEngine(
            base_url=base_url,
            api_key=api_key or "none",
            model=model,
            extra_headers=extra_headers,
        )

    # 默认 claude_cli（extra_headers 静默忽略）
    model = await get_task_model(session, model_key or MODEL_CHAT_KEY)
    return get_engine("claude_cli", model=model)
