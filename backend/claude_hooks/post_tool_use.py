#!/usr/bin/env python3
"""PostToolUse hook：落盘脱敏 + 敏感值输出审计。

Write / Edit / MultiEdit 写入文件后，原地替换文件中的敏感 KEY=value 行。
Bash stdout 中检测到凭据值模式时写审计日志。
Read 工具访问可疑文件名时写审计日志。

注：updatedToolOutput 在 CLI 2.1.197 实测无效，stdout 脱敏暂只做审计记录；
    文件落盘脱敏不依赖 updatedToolOutput，直接读写磁盘，当前版本即可生效。
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/claude_hooks")
from _audit import audit, hook_log  # noqa: E402

# 落盘脱敏：精确 key 名集合（高确信度，不会误判）
_SENSITIVE_ENV_KEYS = frozenset({
    "JWT_SECRET",
    "DATABASE_URL",
    "ADMIN_PASSWORD",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "SMTP_PASSWORD",
    # OpenAI / Azure / Google 常见 key 名
    "OPENAI_API_KEY",
    "AZURE_OPENAI_API_KEY",
    "AZURE_CLIENT_SECRET",
    "GOOGLE_API_KEY",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "VERTEX_AI_KEY",
    "GCP_SERVICE_ACCOUNT_KEY",
})

# 语义后缀兜底：匹配 KEY=value 行中 key 名含敏感后缀的行
# 优先级低于精确集合，但能覆盖未来任何新服务商
_SENSITIVE_KEY_SUFFIX_RE = re.compile(
    r"^[A-Z][A-Z0-9_]*_"
    r"(?:API_KEY|SECRET_KEY|ACCESS_KEY|AUTH_TOKEN|API_TOKEN|"
    r"SECRET|PASSWORD|CREDENTIAL|PRIVATE_KEY|CLIENT_SECRET)$"
)

# 凭据值特征模式（兜底，不依赖 key 名）
_VALUE_PATTERNS = (
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), "anthropic_api_key"),
    (re.compile(r"sk-proj-[A-Za-z0-9\-_]{20,}"), "openai_project_key"),
    # OpenAI standard key（sk- 前缀，48 字符以上，避免误判短字符串）
    (re.compile(r"sk-[A-Za-z0-9]{48,}"), "openai_api_key_candidate"),
    (re.compile(r"AKIA[A-Z0-9]{16}"), "aws_access_key_id"),
    (re.compile(r"[A-Za-z0-9/+]{40}\b"), "aws_secret_access_key_candidate"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "github_oauth_token"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "github_personal_token"),
    # Google Cloud API key（AIza 前缀）
    (re.compile(r"AIza[A-Za-z0-9\-_]{35,}"), "google_api_key"),
    # Azure 格式（32 位 hex 或带连字符的 UUID）
    (re.compile(r"\b[0-9a-f]{32}\b"), "azure_key_candidate"),
    (re.compile(r"postgresql\+[a-z]+://[^@\s]+:[^@\s]+@"), "db_url_with_password"),
    # 通用 Bearer token（Authorization 头泄漏）
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_\.]{20,}"), "bearer_token"),
)

# Read 工具可疑文件名模式
_SUSPICIOUS_READ_PATTERNS = (
    re.compile(r"env[^/]*\.txt$", re.IGNORECASE),
    re.compile(r"\.env(\.[^/]+)?$"),
    re.compile(r"/proc/(?:self|\d+)/environ"),
)


def _redact_file(file_path: str) -> list[str]:
    """读取文件，将 SENSITIVE_ENV_KEYS 中的 KEY=value 行替换为 KEY=[REDACTED]，原地写回。
    返回命中的 key 名列表（不含值）。"""
    try:
        path = Path(file_path)
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    hit_keys: list[str] = []
    changed = False

    for line in lines:
        if "=" in line:
            key = line.partition("=")[0].strip()
            if key in _SENSITIVE_ENV_KEYS or _SENSITIVE_KEY_SUFFIX_RE.match(key):
                out.append(f"{key}=[REDACTED]\n")
                hit_keys.append(key)
                changed = True
                continue
        out.append(line)

    if changed:
        try:
            path.write_text("".join(out), encoding="utf-8")
        except OSError:
            pass

    return hit_keys


def _scan_value_patterns(text: str) -> list[str]:
    """扫描文本中的凭据值特征，返回命中的模式标签列表（不含原始值）。"""
    return [label for pattern, label in _VALUE_PATTERNS if pattern.search(text)]


def _handle_write(payload: dict, tool_input: dict) -> None:
    tool_name = payload.get("tool_name", "Write")
    file_path = tool_input.get("file_path", "") or ""
    user = os.environ.get("KB_AGENT_AUDIT_USER") or "unknown"
    session_id = payload.get("session_id")

    if not file_path:
        hook_log("post", tool_name, "allow", {"user": user, "session_id": session_id, "file_path": "", "note": "no file_path"})
        return

    hit_keys = _redact_file(file_path)
    if hit_keys:
        hook_log("post", tool_name, "redact", {"user": user, "session_id": session_id, "file_path": file_path, "redacted_keys": hit_keys})
        audit("sensitive_key_redacted_in_file", {"user": user, "session_id": session_id, "file_path": file_path, "redacted_keys": hit_keys, "tool_name": tool_name})
    else:
        hook_log("post", tool_name, "allow", {"user": user, "session_id": session_id, "file_path": file_path})


def _extract_redirect_files(command: str, cwd: str | None) -> list[str]:
    """从 bash 命令中提取 > / >> / tee 的目标文件路径列表。"""
    files: list[str] = []
    # 匹配 > file 或 >> file（跳过 &> /dev/null 等）
    for m in re.finditer(r">{1,2}\s*([^&\s|;><][^\s|;><]*)", command):
        target = m.group(1).strip()
        if target and target != "/dev/null":
            files.append(target)
    # 匹配 tee [-a] file
    for m in re.finditer(r"\btee\s+(?:-a\s+)?([^\s|;><]+)", command):
        files.append(m.group(1).strip())
    # 相对路径加上 cwd
    resolved = []
    for f in files:
        if not f.startswith("/") and cwd:
            resolved.append(str(Path(cwd) / f))
        else:
            resolved.append(f)
    return resolved


def _handle_bash(payload: dict, tool_response: dict) -> None:
    stdout = tool_response.get("stdout", "") or ""
    stderr = tool_response.get("stderr", "") or ""
    combined = stdout + "\n" + stderr
    user = os.environ.get("KB_AGENT_AUDIT_USER") or "unknown"
    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    command = (payload.get("tool_input", {}) or {}).get("command", "")

    # 1. 扫 stdout/stderr 中的凭据值特征
    stdout_hits = _scan_value_patterns(combined)

    # 2. 对重定向目标文件做落盘脱敏（shell 重定向时 stdout 为空，输出全写进文件）
    redirect_files = _extract_redirect_files(command, cwd)
    all_redacted: dict[str, list[str]] = {}
    for fpath in redirect_files:
        hit_keys = _redact_file(fpath)
        # 同时用值特征模式扫文件内容（兜底，KEY 名脱敏之外的值）
        try:
            content = Path(fpath).read_text(encoding="utf-8", errors="replace")
            val_hits = _scan_value_patterns(content)
        except OSError:
            val_hits = []
        if hit_keys or val_hits:
            all_redacted[fpath] = hit_keys + val_hits

    verdict = "allow"
    if stdout_hits or all_redacted:
        verdict = "redact" if all_redacted else "audit"

    hook_log("post", "Bash", verdict, {
        "user": user,
        "session_id": session_id,
        "cwd": cwd,
        "command": command[:500],
        "stdout_len": len(stdout),
        "stdout_pattern_hits": stdout_hits,
        "redirect_files": redirect_files,
        "redacted_files": all_redacted,
    })

    if stdout_hits:
        audit("env_value_in_output", {
            "user": user, "session_id": session_id, "cwd": cwd,
            "pattern_types": stdout_hits, "command": command[:500],
        })
    for fpath, keys in all_redacted.items():
        audit("sensitive_key_redacted_in_file", {
            "user": user, "session_id": session_id,
            "file_path": fpath, "redacted_keys": keys, "tool_name": "Bash",
        })


def _handle_read(payload: dict, tool_input: dict) -> None:
    file_path = tool_input.get("file_path", "") or ""
    user = os.environ.get("KB_AGENT_AUDIT_USER") or "unknown"
    session_id = payload.get("session_id")

    suspicious = any(p.search(file_path) for p in _SUSPICIOUS_READ_PATTERNS)
    hook_log("post", "Read", "audit" if suspicious else "allow", {
        "user": user,
        "session_id": session_id,
        "file_path": file_path,
        "suspicious": suspicious,
    })
    if suspicious:
        audit("suspicious_file_read", {"user": user, "session_id": session_id, "file_path": file_path})


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}

    if tool_name in ("Write", "Edit", "MultiEdit"):
        _handle_write(payload, tool_input)
    elif tool_name == "Bash":
        _handle_bash(payload, tool_response)
    elif tool_name == "Read":
        _handle_read(payload, tool_input)

    return 0


if __name__ == "__main__":
    sys.exit(main())
