"""ClaudeCliEngine —— 以子进程方式调用 `claude` CLI。

安全要点：
- 用 argv 列表传参，绝不用 shell=True / 字符串拼接（防命令注入，见 SECURITY #2）。
- 设置超时，超时/非零退出码都抛出清晰错误。
"""

import asyncio
from pathlib import Path

from app.core.config import get_settings
from app.engine.base import EngineResult


class EngineError(RuntimeError):
    """引擎调用失败。"""


class ClaudeCliEngine:
    """封装 Claude CLI 子进程调用。"""

    def __init__(self) -> None:
        settings = get_settings()
        self._cli_path = settings.claude_cli_path
        self._model = settings.claude_model
        self._timeout = settings.engine_timeout_sec

    def _build_argv(self, prompt: str, files: list[Path] | None) -> list[str]:
        """构造 argv 列表；参数以独立元素传入，避免 shell 解析。"""
        argv: list[str] = [self._cli_path, "-p", prompt]
        if self._model:
            argv += ["--model", self._model]
        # 附加文件路径作为独立参数（不拼接进命令字符串）
        for f in files or []:
            argv += ["--file", str(f)]
        return argv

    async def complete(
        self,
        prompt: str,
        *,
        files: list[Path] | None = None,
        system: str | None = None,
    ) -> EngineResult:
        argv = self._build_argv(prompt, files)
        if system:
            argv += ["--append-system-prompt", system]

        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except TimeoutError as exc:
            raise EngineError(f"Claude CLI 调用超时（>{self._timeout}s）") from exc
        except FileNotFoundError as exc:
            raise EngineError(f"找不到 Claude CLI: {self._cli_path!r}") from exc

        if proc.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise EngineError(f"Claude CLI 返回非零退出码 {proc.returncode}: {detail}")

        return EngineResult(text=stdout.decode("utf-8", errors="replace").strip())
