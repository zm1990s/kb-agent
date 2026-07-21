#!/usr/bin/env python3
"""PostToolUse hook（Codex CLI）：落盘脱敏 + 敏感值输出审计。

输入格式（Codex CLI）：
  {"hook_event_name": "PostToolUse", "tool_name": "Bash",
   "tool_input": {"command": "..."}, "tool_response": {"output": "..."},
   "session_id": "...", "cwd": "..."}

Codex PostToolUse 的 tool_response 字段名为 "output"（非 stdout/stderr）。
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/codex_hooks")
from _audit import audit, hook_log  # noqa: E402

_SENSITIVE_ENV_KEYS = frozenset({
    "JWT_SECRET", "DATABASE_URL", "ADMIN_PASSWORD",
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
    "SMTP_PASSWORD",
    "OPENAI_API_KEY", "AZURE_OPENAI_API_KEY", "AZURE_CLIENT_SECRET",
    "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
    "VERTEX_AI_KEY", "GCP_SERVICE_ACCOUNT_KEY",
})

_SENSITIVE_KEY_SUFFIX_RE = re.compile(
    r"^[A-Z][A-Z0-9_]*_"
    r"(?:API_KEY|SECRET_KEY|ACCESS_KEY|AUTH_TOKEN|API_TOKEN|"
    r"SECRET|PASSWORD|CREDENTIAL|PRIVATE_KEY|CLIENT_SECRET)$"
)

_VALUE_PATTERNS = (
    (re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"), "anthropic_api_key"),
    (re.compile(r"sk-proj-[A-Za-z0-9\-_]{20,}"), "openai_project_key"),
    (re.compile(r"sk-[A-Za-z0-9]{48,}"), "openai_api_key_candidate"),
    (re.compile(r"AKIA[A-Z0-9]{16}"), "aws_access_key_id"),
    (re.compile(r"[A-Za-z0-9/+]{40}\b"), "aws_secret_access_key_candidate"),
    (re.compile(r"gho_[A-Za-z0-9]{20,}"), "github_oauth_token"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "github_personal_token"),
    (re.compile(r"AIza[A-Za-z0-9\-_]{35,}"), "google_api_key"),
    (re.compile(r"\b[0-9a-f]{32}\b"), "azure_key_candidate"),
    (re.compile(r"postgresql\+[a-z]+://[^@\s]+:[^@\s]+@"), "db_url_with_password"),
    (re.compile(r"Bearer\s+[A-Za-z0-9\-_\.]{20,}"), "bearer_token"),
)

_SUSPICIOUS_READ_PATTERNS = (
    re.compile(r"env[^/]*\.txt$", re.IGNORECASE),
    re.compile(r"\.env(\.[^/]+)?$"),
    re.compile(r"/proc/(?:self|\d+)/environ"),
)


def _redact_file(file_path: str) -> list[str]:
    try:
        path = Path(file_path)
        if not path.is_file():
            return []
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines(keepends=True)
    out, hit_keys, changed = [], [], False
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
    return [label for pattern, label in _VALUE_PATTERNS if pattern.search(text)]


def _extract_redirect_files(command: str, cwd: str | None) -> list[str]:
    files: list[str] = []
    for m in re.finditer(r">{1,2}\s*([^&\s|;><][^\s|;><]*)", command):
        target = m.group(1).strip()
        if target and target != "/dev/null":
            files.append(target)
    for m in re.finditer(r"\btee\s+(?:-a\s+)?([^\s|;><]+)", command):
        files.append(m.group(1).strip())
    resolved = []
    for f in files:
        if not f.startswith("/") and cwd:
            resolved.append(str(Path(cwd) / f))
        else:
            resolved.append(f)
    return resolved


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}

    user = os.environ.get("KB_AGENT_AUDIT_USER") or "unknown"
    session_id = payload.get("session_id")
    cwd = payload.get("cwd")

    if tool_name != "Bash":
        return 0

    # Codex PostToolUse: tool_response 有 "output" 字段（合并了 stdout/stderr）
    output = tool_response.get("output", "") or ""
    command = (tool_input.get("command", "") or "")[:500]

    stdout_hits = _scan_value_patterns(output)
    redirect_files = _extract_redirect_files(command, cwd)
    all_redacted: dict[str, list[str]] = {}
    for fpath in redirect_files:
        hit_keys = _redact_file(fpath)
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
        "user": user, "session_id": session_id, "cwd": cwd,
        "command": command,
        "output_len": len(output),
        "output_pattern_hits": stdout_hits,
        "redirect_files": redirect_files,
        "redacted_files": all_redacted,
    })

    if stdout_hits:
        audit("env_value_in_output", {
            "user": user, "session_id": session_id, "cwd": cwd,
            "pattern_types": stdout_hits, "command": command,
        })
    for fpath, keys in all_redacted.items():
        audit("sensitive_key_redacted_in_file", {
            "user": user, "session_id": session_id,
            "file_path": fpath, "redacted_keys": keys, "tool_name": "Bash",
        })

    return 0


if __name__ == "__main__":
    sys.exit(main())
