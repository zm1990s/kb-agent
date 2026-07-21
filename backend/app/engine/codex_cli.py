"""CodexCliEngine —— 以子进程方式调用 Codex CLI（codex exec）。

安全要点：
- 用 argv 列表传参，绝不用 shell=True（防命令注入）。
- 环境白名单：只透传 OPENAI_* 和系统运行变量，剥离 JWT_SECRET / DATABASE_URL 等。
- 通过 CODEX_HOME 指向挂载的配置目录（Azure 认证 + hooks 注册）。
- 以活动超时（idle timeout）代替固定总超时。
"""

import asyncio
import json
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path

from app.core.config import get_settings
from app.engine.base import EngineError, EngineResult, TextChunk, ThinkingChunk

logger = logging.getLogger(__name__)

# 子进程环境白名单
_CLI_ENV_EXACT = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM", "TMPDIR",
)
_CLI_ENV_PREFIXES = ("OPENAI_",)


def _build_cli_env(codex_config_dir: str, audit_user: str | None = None) -> dict[str, str]:
    """构造传给 codex 子进程的精简环境（白名单透传）。

    CODEX_HOME 指向挂载的配置目录，Codex CLI 从中读取 config.toml / hooks.json。
    """
    out = {k: os.environ[k] for k in _CLI_ENV_EXACT if k in os.environ}
    for k, v in os.environ.items():
        if k.startswith(_CLI_ENV_PREFIXES):
            out[k] = v
    out["CODEX_HOME"] = codex_config_dir
    if audit_user:
        out["KB_AGENT_AUDIT_USER"] = audit_user
    return out


def _build_prompt(prompt: str, system: str | None) -> str:
    """将 system prompt 拼入 prompt 前缀（Codex CLI 无 --system-prompt flag）。"""
    if not system:
        return prompt
    return f"<system>\n{system}\n</system>\n\n{prompt}"


class CodexCliEngine:
    """封装 Codex CLI 子进程调用（codex exec）。"""

    def __init__(
        self,
        model: str | None = None,
        audit_user: str | None = None,
        idle_timeout_sec: int | None = None,
    ) -> None:
        settings = get_settings()
        self._cli_path = settings.codex_cli_path
        self._config_dir = settings.codex_config_dir
        self._idle_timeout = (
            idle_timeout_sec if idle_timeout_sec is not None
            else settings.engine_idle_timeout_sec
        )
        self._stream_limit = settings.engine_stream_limit_bytes
        self._audit_user = audit_user
        self._model = model or ""

    def _build_argv_base(
        self, files: list[Path] | None, cwd: Path | None
    ) -> list[str]:
        """构造不含 prompt 和输出模式的公共参数列表。"""
        files = files or []
        argv: list[str] = [self._cli_path, "exec"]

        if self._model:
            argv += ["-m", self._model]
        if cwd is not None:
            argv += ["-C", str(cwd)]
        for f in files:
            argv += ["--add-dir", str(f.parent)]
        # 容器内始终跳过交互审批和沙箱（非交互自动化环境）
        argv += ["--dangerously-bypass-approvals-and-sandbox"]
        # 容器内受控环境，跳过 hook trust review（hook 已通过 CODEX_HOME 注册）
        argv += ["--dangerously-bypass-hook-trust"]
        if files or cwd is not None:
            argv += ["--skip-git-repo-check"]
        return argv

    async def complete(
        self,
        prompt: str,
        *,
        files: list[Path] | None = None,
        system: str | None = None,
        cwd: Path | None = None,
    ) -> EngineResult:
        full_prompt = _build_prompt(prompt, system)
        if files:
            listing = "\n".join(f"- {f}" for f in files)
            full_prompt = f"{full_prompt}\n\n请阅读以下本地文件后作答：\n{listing}"

        argv = self._build_argv_base(files, cwd)
        argv += ["--json"]
        argv.append(full_prompt)

        argv_log = [a if a != full_prompt else f"<prompt:{len(full_prompt)}chars>" for a in argv]
        logger.debug("Codex CLI 启动: %s", argv_log)

        env = _build_cli_env(self._config_dir, self._audit_user)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd) if cwd is not None else None,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self._stream_limit,
            )
        except FileNotFoundError as exc:
            raise EngineError(f"找不到 Codex CLI: {self._cli_path!r}") from exc

        if proc.stdout is None:
            proc.kill()
            await proc.wait()
            raise EngineError("无法读取 Codex CLI 输出（stdout 为空）")

        idle = self._idle_timeout
        lines: list[bytes] = []
        timed_out = False
        try:
            while True:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=idle)
                if not line:
                    break
                lines.append(line)
        except TimeoutError:
            timed_out = True
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

        if timed_out:
            raise EngineError(f"Codex CLI 超过 {idle}s 无输出，判定为无响应")

        stderr_bytes = await asyncio.wait_for(proc.stderr.read(), timeout=idle)
        await proc.wait()

        if proc.returncode != 0:
            stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
            stdout_tail = b"".join(lines).decode("utf-8", errors="replace").strip()
            detail = stderr_str or stdout_tail or "(无输出)"
            logger.error(
                "Codex CLI 失败 | 退出码=%d | argv=%s | stderr=%r | stdout=%r",
                proc.returncode, argv_log, stderr_str[:500], stdout_tail[:500],
            )
            raise EngineError(f"Codex CLI 返回非零退出码 {proc.returncode}: {detail}")

        # 从 JSONL 中取最后一条 agent_message
        text = ""
        for raw in lines:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "item.completed":
                item = obj.get("item", {})
                if item.get("type") == "agent_message":
                    text = item.get("text", "")
            elif obj.get("type") == "error":
                raise EngineError(f"Codex CLI 返回错误: {obj.get('message', obj)}")

        return EngineResult(text=text.strip())

    async def complete_streaming(
        self,
        prompt: str,
        *,
        system: str | None = None,
        files: list[Path] | None = None,
        cwd: Path | None = None,
    ) -> AsyncGenerator[ThinkingChunk | TextChunk, None]:
        """流式调用：解析 codex exec --json 的 JSONL 输出，yield TextChunk。

        Codex CLI 不产生 thinking 输出，ThinkingChunk 永不 yield。
        """
        full_prompt = _build_prompt(prompt, system)
        if files:
            listing = "\n".join(f"- {f}" for f in files)
            full_prompt = f"{full_prompt}\n\n请阅读以下本地文件后作答：\n{listing}"

        argv = self._build_argv_base(files, cwd)
        argv += ["--json"]
        argv.append(full_prompt)

        argv_log = [a if a != full_prompt else f"<prompt:{len(full_prompt)}chars>" for a in argv]
        logger.debug("Codex CLI 流式启动: %s", argv_log)

        env = _build_cli_env(self._config_dir, self._audit_user)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(cwd) if cwd is not None else None,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self._stream_limit,
            )
        except FileNotFoundError as exc:
            raise EngineError(f"找不到 Codex CLI: {self._cli_path!r}") from exc

        if proc.stdout is None:
            proc.kill()
            await proc.wait()
            raise EngineError("无法读取 Codex CLI 流式输出（stdout 为空）")

        idle = self._idle_timeout
        timed_out = False
        stderr_task = asyncio.ensure_future(proc.stderr.read())  # type: ignore[union-attr]

        try:
            while True:
                try:
                    line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=idle)
                except TimeoutError:
                    timed_out = True
                    break

                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Codex --json 事件格式（v0.144+）
                # {"type":"item.completed","item":{"type":"agent_message","text":"..."}}
                event_type = obj.get("type", "")

                if event_type == "item.completed":
                    item = obj.get("item", {})
                    if item.get("type") == "agent_message":
                        text = item.get("text", "")
                        if text:
                            yield TextChunk(text=text)

                elif event_type == "error":
                    raise EngineError(f"Codex CLI 返回错误: {obj.get('message', obj)}")

                # function_call / function_call_output 等事件静默忽略

        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

        if timed_out:
            raise EngineError(f"Codex CLI 流式超过 {idle}s 无输出，判定为无响应")

        stderr_bytes = await asyncio.wait_for(stderr_task, timeout=idle)
        await proc.wait()

        if proc.returncode != 0:
            stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
            logger.error(
                "Codex CLI 流式失败 | 退出码=%d | stderr=%r",
                proc.returncode, stderr_str[:500],
            )
            raise EngineError(
                f"Codex CLI 返回非零退出码 {proc.returncode}: {stderr_str or '(无输出)'}"
            )
