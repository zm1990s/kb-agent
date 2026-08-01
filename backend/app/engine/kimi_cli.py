"""KimiCliEngine —— 以子进程方式调用 Kimi Code CLI（kimi -p ...）。

安全要点：
- 用 argv 列表传参，绝不用 shell=True（防命令注入）。
- 环境白名单：只透传 KIMI_* / MOONSHOT_* 和系统运行变量，剥离 JWT_SECRET / DATABASE_URL 等。
- 通过 KIMI_CODE_HOME 指向挂载的配置目录（API key + 模型定义在 config.toml 中）。
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
_CLI_ENV_PREFIXES = ("KIMI_", "MOONSHOT_")


def _build_cli_env(kimi_config_dir: str, audit_user: str | None = None) -> dict[str, str]:
    """构造传给 kimi 子进程的精简环境（白名单透传）。

    KIMI_CODE_HOME 指向挂载的配置目录，Kimi CLI 从中读取 config.toml（含 API key / 模型定义）。
    """
    out = {k: os.environ[k] for k in _CLI_ENV_EXACT if k in os.environ}
    for k, v in os.environ.items():
        if k.startswith(_CLI_ENV_PREFIXES):
            out[k] = v
    out["KIMI_CODE_HOME"] = kimi_config_dir
    if audit_user:
        out["KB_AGENT_AUDIT_USER"] = audit_user
    return out


def _build_prompt(prompt: str, system: str | None) -> str:
    """将 system prompt 拼入 prompt 前缀（Kimi CLI 无 --system-prompt flag）。"""
    if not system:
        return prompt
    return f"<system>\n{system}\n</system>\n\n{prompt}"


class KimiCliEngine:
    """封装 Kimi Code CLI 子进程调用（kimi -p <prompt> --output-format stream-json）。"""

    def __init__(
        self,
        model: str | None = None,
        audit_user: str | None = None,
        idle_timeout_sec: int | None = None,
    ) -> None:
        settings = get_settings()
        self._cli_path = settings.kimi_cli_path
        self._config_dir = settings.kimi_config_dir
        self._idle_timeout = (
            idle_timeout_sec if idle_timeout_sec is not None
            else settings.engine_idle_timeout_sec
        )
        self._stream_limit = settings.engine_stream_limit_bytes
        self._audit_user = audit_user
        self._model = model or ""

    def _build_argv(
        self, full_prompt: str, files: list[Path] | None, cwd: Path | None
    ) -> list[str]:
        """构造完整 argv 列表。

        kimi -p 直接跟 prompt 字符串（不同于 codex exec 的 positional arg）。
        --auto 完全自主模式，不产生交互提问。
        --output-format stream-json 输出 NDJSON，每行一个 JSON 事件。
        """
        files = files or []
        argv: list[str] = [self._cli_path, "-p", full_prompt]

        if self._model:
            argv += ["-m", self._model]

        argv += ["--output-format", "stream-json"]

        for f in files:
            argv += ["--add-dir", str(f.parent)]
        if cwd is not None:
            argv += ["--add-dir", str(cwd)]

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

        argv = self._build_argv(full_prompt, files, cwd)

        argv_log = [a if a != full_prompt else f"<prompt:{len(full_prompt)}chars>" for a in argv]
        logger.debug("Kimi CLI 启动: %s", argv_log)

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
            raise EngineError(f"找不到 Kimi CLI: {self._cli_path!r}") from exc

        if proc.stdout is None:
            proc.kill()
            await proc.wait()
            raise EngineError("无法读取 Kimi CLI 输出（stdout 为空）")

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
            raise EngineError(f"Kimi CLI 超过 {idle}s 无输出，判定为无响应")

        stderr_bytes = await asyncio.wait_for(proc.stderr.read(), timeout=idle)
        await proc.wait()

        if proc.returncode != 0:
            stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
            stdout_tail = b"".join(lines).decode("utf-8", errors="replace").strip()
            detail = stderr_str or stdout_tail or "(无输出)"
            logger.error(
                "Kimi CLI 失败 | 退出码=%d | argv=%s | stderr=%r | stdout=%r",
                proc.returncode, argv_log, stderr_str[:500], stdout_tail[:500],
            )
            raise EngineError(f"Kimi CLI 返回非零退出码 {proc.returncode}: {detail}")

        # 从 NDJSON 中取 role=="assistant" 的最后一条
        # 格式：{"role":"assistant","content":"<完整文本>"}
        text = ""
        for raw in lines:
            line_str = raw.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue
            try:
                obj = json.loads(line_str)
            except json.JSONDecodeError:
                continue
            if obj.get("role") == "assistant":
                text = obj.get("content", "")

        return EngineResult(text=text.strip())

    async def complete_streaming(
        self,
        prompt: str,
        *,
        system: str | None = None,
        files: list[Path] | None = None,
        cwd: Path | None = None,
    ) -> AsyncGenerator[ThinkingChunk | TextChunk, None]:
        """流式调用：解析 kimi --output-format stream-json 的 NDJSON 输出，yield TextChunk。

        Kimi CLI stream-json 一次性输出完整文本（非增量 delta），每行一个 JSON 事件。
        ThinkingChunk 暂不 yield（Kimi CLI 目前不在 stream-json 中单独输出 thinking）。
        """
        full_prompt = _build_prompt(prompt, system)
        if files:
            listing = "\n".join(f"- {f}" for f in files)
            full_prompt = f"{full_prompt}\n\n请阅读以下本地文件后作答：\n{listing}"

        argv = self._build_argv(full_prompt, files, cwd)

        argv_log = [a if a != full_prompt else f"<prompt:{len(full_prompt)}chars>" for a in argv]
        logger.debug("Kimi CLI 流式启动: %s", argv_log)

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
            raise EngineError(f"找不到 Kimi CLI: {self._cli_path!r}") from exc

        if proc.stdout is None:
            proc.kill()
            await proc.wait()
            raise EngineError("无法读取 Kimi CLI 流式输出（stdout 为空）")

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

                # Kimi stream-json 格式：
                # {"role":"assistant","content":"<完整文本>"}  — 最终回答
                # {"role":"meta","type":"session.resume_hint",...}  — 元数据，忽略
                if obj.get("role") == "assistant":
                    text = obj.get("content", "")
                    if text:
                        yield TextChunk(text=text)

        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

        if timed_out:
            raise EngineError(f"Kimi CLI 流式超过 {idle}s 无输出，判定为无响应")

        stderr_bytes = await asyncio.wait_for(stderr_task, timeout=idle)
        await proc.wait()

        if proc.returncode != 0:
            stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
            logger.error(
                "Kimi CLI 流式失败 | 退出码=%d | stderr=%r",
                proc.returncode, stderr_str[:500],
            )
            raise EngineError(
                f"Kimi CLI 返回非零退出码 {proc.returncode}: {stderr_str or '(无输出)'}"
            )
