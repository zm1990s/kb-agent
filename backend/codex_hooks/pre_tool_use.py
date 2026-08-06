#!/usr/bin/env python3
"""PreToolUse hook（Codex CLI）：拦截读取环境变量及路径越界访问。

输入格式（Codex CLI）：
  {"hook_event_name": "PreToolUse", "tool_name": "Bash",
   "tool_input": {"command": "..."}, "session_id": "...", "cwd": "..."}

命中时输出 deny JSON 并 exit 0（Codex 读 stdout 判断决策）。
未命中 exit 0 + 空输出（放行）。
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/codex_hooks")
from _audit import audit, hook_log  # noqa: E402

_DENY_REASON_ENV = (
    "Platform policy violation: reading environment variables is prohibited. "
    "This event has been logged. Please continue without accessing the "
    "environment; inform the user that this action was blocked and recorded."
)
_DENY_REASON_PATH = (
    "Platform policy violation: file access outside the authorized workspace "
    "directory is prohibited. This event has been logged. Please only access "
    "files within the designated workspace; inform the user that this action "
    "was blocked and recorded."
)

# ── 与 claude_hooks/pre_tool_use.py 相同的检测规则 ───────────────────────────
_CMD_START = r"(?:^|[\n;&|]|\|\||&&|\bsudo\s+|\bnohup\s+|\bexec\s+)\s*"
_PATTERNS = (
    re.compile(_CMD_START + r"(?:env|printenv)(?:\s|$)"),
    re.compile(r"/proc/(?:self|\d+|\$\$|\$\{?[A-Za-z_]\w*\}?)/environ"),
    re.compile(r"os\.environ\b|os\.environb\b|os\.getenv\s*\("),
    re.compile(r"process\.env\b"),
    re.compile(r"\bgetenv\s*\("),
    re.compile(r"\bos\.Getenv\s*\(|\bos\.Environ\s*\("),
    re.compile(r"\bload_dotenv\s*\("),
    re.compile(r"\%ENV\b|\$ENV\s*\{"),
    re.compile(r"\bENV\s*[\[.]"),
    re.compile(r"\bENVIRON\b"),
    re.compile(r"\$_ENV\b|\$_SERVER\b"),
    re.compile(r"\$env\s*\(|\barray\s+get\s+env\b"),
    re.compile(r"\bSys\.getenv\s*\("),
    re.compile(r"\$env:|\bGet-ChildItem\s+env:|\bGetEnvironmentVariables\s*\("),
    re.compile(_CMD_START + r"declare\s+-[pPxX]\b"),
    re.compile(_CMD_START + r"compgen\s+-v\b"),
    re.compile(_CMD_START + r"export\s+-[pP]\b"),
    re.compile(_CMD_START + r"jq\b[^|;&\n]*\benv\b"),
    re.compile(
        r"\$\{?(?:"
        r"ANTHROPIC|CLAUDE|"
        r"AWS|"
        r"AZURE|"
        r"OPENAI|"
        r"GOOGLE|GCP|GCLOUD|VERTEX|GEMINI|"
        r"COHERE|"
        r"HUGGINGFACE|HF_|"
        r"REPLICATE|"
        r"TOGETHER|TOGETHERAI|"
        r"MISTRAL|"
        r"GROQ|"
        r"DEEPSEEK|"
        r"PERPLEXITY|"
        r"BEDROCK|SAGEMAKER"
        r")[A-Za-z0-9_]*"
    ),
    re.compile(
        r"\$\{?[A-Z][A-Z0-9_]*_"
        r"(?:API_KEY|SECRET_KEY|ACCESS_KEY|AUTH_TOKEN|API_TOKEN|"
        r"SECRET|PASSWORD|CREDENTIAL|PRIVATE_KEY|CLIENT_SECRET)"
        r"(?:\}|[^A-Z0-9_]|$)"
    ),
)

# ── 路径越界检查 ──────────────────────────────────────────────────────────────
_ABS_PATH_RE = re.compile(
    r'(?<![/\w])/(?:data|etc|home|root|proc|var|tmp|app)/[^\s|;&><"\'\n]+'
)

_SCRIPT_INTERPRETERS = frozenset({
    "python", "python3", "node", "ruby", "perl",
    "bash", "sh", "zsh", "ksh", "fish",
    "lua", "luajit", "tclsh", "wish",
    "Rscript", "rscript", "pwsh", "powershell", "php", "groovy",
})
_SCRIPT_FLAG_INTERPRETERS = frozenset({"awk", "gawk", "nawk", "mawk"})

_PATH_REASON_LABELS = frozenset({
    "file_access_outside_workspace",
    "file_read_outside_workspace",
    "file_path_outside_workspace_in_written_content",
    "file_path_outside_workspace_in_executed_script",
})


def _matches_pattern(text: str) -> bool:
    return any(p.search(text) for p in _PATTERNS)


def _extract_inline_code(command: str) -> str:
    m = re.search(
        r"(?:python[23]?|node|bash|sh|zsh|ksh|fish|perl|ruby|lua|luajit|php|pwsh|powershell|tclsh|Rscript)\s+-[cCeErR](?:ommand)?\s+(['\"])(.*?)\1",
        command, re.DOTALL,
    )
    return m.group(2) if m else ""


def _read_and_check(path: str) -> tuple[bool, str]:
    """读取脚本文件，检查 env 访问模式和越界路径。返回 (命中, 原因标签)。"""
    try:
        content = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False, ""
    if _matches_pattern(content):
        return True, "env_read_in_executed_script"
    allowed = _get_allowed_dirs()
    if allowed:
        for m in _ABS_PATH_RE.finditer(content):
            if not _path_allowed(m.group(0), allowed):
                return True, "file_path_outside_workspace_in_executed_script"
    return False, ""


def _check_script_content(command: str) -> tuple[bool, str]:
    tokens = command.split()
    if not tokens:
        return False, ""
    interpreter = os.path.basename(tokens[0])
    if interpreter in _SCRIPT_FLAG_INTERPRETERS:
        for i, tok in enumerate(tokens[1:], 1):
            if tok == "-f" and i + 1 < len(tokens):
                return _read_and_check(tokens[i + 1])
            if tok.startswith("-f") and len(tok) > 2:
                return _read_and_check(tok[2:])
        m = re.search(r"""awk\s+(['"'])(.*?)\1""", command, re.DOTALL)
        if m:
            if _matches_pattern(m.group(2)):
                return True, "env_read_in_executed_script"
        return False, ""
    if interpreter not in _SCRIPT_INTERPRETERS:
        return False, ""
    for tok in tokens[1:]:
        if tok.startswith("-"):
            continue
        return _read_and_check(tok)
    return False, ""


def _get_allowed_dirs() -> list[Path]:
    """从 KB_AGENT_ALLOWED_DIRS 读取授权目录列表（冒号分隔），resolve() 规范化。
    未设置时返回空列表（不拦截，向后兼容）。
    """
    raw = os.environ.get("KB_AGENT_ALLOWED_DIRS", "")
    result = []
    for p in raw.split(":"):
        p = p.strip()
        if p:
            try:
                result.append(Path(p).resolve())
            except (OSError, ValueError):
                pass
    return result


def _path_allowed(file_path: str, allowed: list[Path]) -> bool:
    """检查 file_path 是否在某个授权目录内（resolve() 后校验 parents）。"""
    try:
        candidate = Path(file_path).resolve()
    except (OSError, ValueError):
        return False
    return any(candidate == d or d in candidate.parents for d in allowed)


def _check_bash(tool_input: dict) -> tuple[bool, str]:
    command = tool_input.get("command", "") or ""
    if _matches_pattern(command):
        return True, "env_read_in_command"
    inline = _extract_inline_code(command)
    if inline and _matches_pattern(inline):
        return True, "env_read_in_inline_code"
    hit, label = _check_script_content(command)
    if hit:
        return True, label
    # 路径越界检查：扫描命令中的绝对路径
    allowed = _get_allowed_dirs()
    if allowed:
        for m in _ABS_PATH_RE.finditer(command):
            if not _path_allowed(m.group(0), allowed):
                return True, "file_access_outside_workspace"
    return False, ""


def _check_read(tool_input: dict) -> tuple[bool, str]:
    """拒绝读取不在授权目录内的文件。"""
    file_path = (tool_input.get("file_path") or "").strip()
    if not file_path:
        return False, ""
    allowed = _get_allowed_dirs()
    if allowed and not _path_allowed(file_path, allowed):
        return True, "file_read_outside_workspace"
    return False, ""


def _deny_reason_for(tool_name: str, reason_label: str) -> str:
    if reason_label in _PATH_REASON_LABELS:
        return _DENY_REASON_PATH
    return _DENY_REASON_ENV


_TOOL_CHECKERS = {
    "Bash": _check_bash,
    "Read": _check_read,
}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}

    checker_fn = _TOOL_CHECKERS.get(tool_name)
    if checker_fn is None:
        return 0

    user = os.environ.get("KB_AGENT_AUDIT_USER") or "unknown"
    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    command = (tool_input.get("command", "") or "")[:2000]
    file_path = tool_input.get("file_path", "") or ""

    hit, reason_label = checker_fn(tool_input)

    hook_log(
        "pre", tool_name,
        "deny" if hit else "allow",
        {
            "user": user,
            "session_id": session_id,
            "cwd": cwd,
            "reason": reason_label or "no_match",
            "command": command,
            "file_path": file_path,
        },
    )

    if not hit:
        return 0

    audit_event = (
        "file_access_blocked" if reason_label in _PATH_REASON_LABELS
        else "env_access_blocked"
    )
    audit(
        audit_event,
        {
            "user": user,
            "session_id": session_id,
            "cwd": cwd,
            "tool_name": tool_name,
            "reason": reason_label,
            "command": command,
            "file_path": file_path,
        },
    )
    deny_reason = _deny_reason_for(tool_name, reason_label)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": deny_reason,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
