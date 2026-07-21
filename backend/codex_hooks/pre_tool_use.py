#!/usr/bin/env python3
"""PreToolUse hook（Codex CLI）：拦截读取环境变量的 Bash 命令。

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

_SCRIPT_INTERPRETERS = frozenset({
    "python", "python3", "node", "ruby", "perl",
    "bash", "sh", "zsh", "ksh", "fish",
    "lua", "luajit", "tclsh", "wish",
    "Rscript", "rscript", "pwsh", "powershell", "php", "groovy",
})
_SCRIPT_FLAG_INTERPRETERS = frozenset({"awk", "gawk", "nawk", "mawk"})


def _matches_pattern(text: str) -> bool:
    return any(p.search(text) for p in _PATTERNS)


def _extract_inline_code(command: str) -> str:
    m = re.search(
        r"(?:python[23]?|node|bash|sh|zsh|ksh|fish|perl|ruby|lua|luajit|php|pwsh|powershell|tclsh|Rscript)\s+-[cCeErR](?:ommand)?\s+(['\"])(.*?)\1",
        command, re.DOTALL,
    )
    return m.group(2) if m else ""


def _read_and_check(path: str) -> bool:
    try:
        return _matches_pattern(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return False


def _check_script_content(command: str) -> bool:
    tokens = command.split()
    if not tokens:
        return False
    interpreter = os.path.basename(tokens[0])
    if interpreter in _SCRIPT_FLAG_INTERPRETERS:
        for i, tok in enumerate(tokens[1:], 1):
            if tok == "-f" and i + 1 < len(tokens):
                return _read_and_check(tokens[i + 1])
            if tok.startswith("-f") and len(tok) > 2:
                return _read_and_check(tok[2:])
        m = re.search(r"""awk\s+(['"'])(.*?)\1""", command, re.DOTALL)
        if m:
            return _matches_pattern(m.group(2))
        return False
    if interpreter not in _SCRIPT_INTERPRETERS:
        return False
    for tok in tokens[1:]:
        if tok.startswith("-"):
            continue
        return _read_and_check(tok)
    return False


def _check_bash(tool_input: dict) -> tuple[bool, str]:
    command = tool_input.get("command", "") or ""
    if _matches_pattern(command):
        return True, "env_read_in_command"
    inline = _extract_inline_code(command)
    if inline and _matches_pattern(inline):
        return True, "env_read_in_inline_code"
    if _check_script_content(command):
        return True, "env_read_in_executed_script"
    return False, ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0

    tool_name = payload.get("tool_name") or ""
    # Codex: tool_input 直接是 dict（与 Claude 相同）
    tool_input = payload.get("tool_input") or {}

    if tool_name != "Bash":
        return 0

    user = os.environ.get("KB_AGENT_AUDIT_USER") or "unknown"
    session_id = payload.get("session_id")
    cwd = payload.get("cwd")
    command = (tool_input.get("command", "") or "")[:2000]

    hit, reason_label = _check_bash(tool_input)

    hook_log(
        "pre", "Bash",
        "deny" if hit else "allow",
        {"user": user, "session_id": session_id, "cwd": cwd,
         "reason": reason_label or "no_match", "command": command},
    )

    if not hit:
        return 0

    audit(
        "env_access_blocked",
        {"user": user, "session_id": session_id, "cwd": cwd,
         "tool_name": "Bash", "reason": reason_label, "command": command},
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": _DENY_REASON_ENV,
        }
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
