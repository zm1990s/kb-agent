"""ClaudeCliEngine —— 以子进程方式调用 `claude` CLI。

安全要点：
- 用 argv 列表传参，绝不用 shell=True / 字符串拼接（防命令注入，见 SECURITY #2）。
- 以活动超时（idle timeout）代替固定总超时：只要 CLI 持续有输出就不判定超时，
  连续无输出超过 ENGINE_IDLE_TIMEOUT_SEC 秒才终止并报错。
"""

import asyncio
import logging
from pathlib import Path

from app.core.config import get_settings
from app.engine.base import EngineResult

logger = logging.getLogger(__name__)


class EngineError(RuntimeError):
    """引擎调用失败。"""


class ClaudeCliEngine:
    """封装 Claude CLI 子进程调用。"""

    def __init__(self) -> None:
        settings = get_settings()
        self._cli_path = settings.claude_cli_path
        self._model = settings.claude_model
        self._idle_timeout = settings.engine_idle_timeout_sec

    def _build_argv(self, prompt: str, files: list[Path] | None) -> list[str]:
        """构造 argv 列表；参数以独立元素传入，避免 shell 解析。

        文件通过"把路径写进 prompt + --add-dir 授权目录"让 CLI 用 Read 工具读原文
        （CLI 的 --file 是 file_id:path 远程资源语义，不适用于本地路径）。
        headless 下用 --permission-mode 跳过交互授权（平台可信，见 SECURITY #2）。
        """
        files = files or []
        full_prompt = prompt
        if files:
            listing = "\n".join(f"- {f}" for f in files)
            full_prompt = (
                f"{prompt}\n\n请阅读以下本地文件后作答：\n{listing}"
            )

        argv: list[str] = [self._cli_path, "-p", full_prompt]
        if self._model:
            argv += ["--model", self._model]
        # 授权每个文件所在目录，供工具访问
        for f in files:
            argv += ["--add-dir", str(f.parent)]
        if files:
            # 放开全部工具（含 Bash，用于 pdftotext 等抽取大文件）。
            # 按项目决策：工具不做限制、假设平台可信（见 SECURITY.md #2）。
            # 注意：该 flag 拒绝 root 运行，容器以非 root 用户启动。
            argv += ["--dangerously-skip-permissions"]
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
        except FileNotFoundError as exc:
            raise EngineError(f"找不到 Claude CLI: {self._cli_path!r}") from exc

        # 逐块读 stdout，每次收到数据就重置空闲计时器。
        # 只有连续 idle_timeout 秒无任何输出才视为卡死并报错。
        chunks: list[bytes] = []
        assert proc.stdout is not None
        idle = self._idle_timeout
        try:
            while True:
                chunk = await asyncio.wait_for(
                    proc.stdout.read(4096), timeout=idle
                )
                if not chunk:
                    break  # EOF
                chunks.append(chunk)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise EngineError(
                f"Claude CLI 超过 {idle}s 无输出，判定为无响应"
            )

        stderr_bytes = await proc.stderr.read()
        await proc.wait()

        if proc.returncode != 0:
            detail = stderr_bytes.decode("utf-8", errors="replace").strip()
            raise EngineError(f"Claude CLI 返回非零退出码 {proc.returncode}: {detail}")

        return EngineResult(text=b"".join(chunks).decode("utf-8", errors="replace").strip())
