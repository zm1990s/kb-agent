#!/usr/bin/env python3
"""PreToolUse hook：拦截读取环境变量的 Bash 命令。

命中 env / printenv / /proc/*/environ / os.environ 等读取环境变量的模式时：
  1. 写安全审计日志；
  2. 输出 deny JSON（英文话术），reason 反馈给模型，模型会转告用户；
未命中则 exit 0 放行。

匹配用「独立命令 token 边界」而非裸子串，避免误伤 `source venv/bin/activate`、
`--env-file`、`python -m venv` 等合法命令（Post hook 会按值兜底脱敏）。
"""

import json
import os
import re
import sys

sys.path.insert(0, "/app/claude_hooks")
from _audit import audit  # noqa: E402

# 违规话术（英文，反馈给模型 → 模型转告用户）
_DENY_REASON = (
    "Platform policy violation: reading environment variables is prohibited. "
    "This event has been logged. Please continue without accessing the "
    "environment; inform the user that this action was blocked and recorded."
)

# 读取环境变量的命令模式（独立命令边界）。
_CMD_START = r"(?:^|[\n;&|]|\|\||&&|\bsudo\s+|\bnohup\s+|\bexec\s+)\s*"
_PATTERNS = (
    # env / printenv 作为独立命令（不匹配 venv / --env-file / conda env 等）
    re.compile(_CMD_START + r"(?:env|printenv)(?:\s|$)"),
    # 读取 /proc/<pid>/environ
    re.compile(r"/proc/(?:self|\d+|\$\$|\$\{?[A-Za-z_]\w*\}?)/environ"),
    # 语言运行时打印环境：os.environ / os.getenv / process.env / getenv(
    re.compile(r"os\.environ|os\.getenv|process\.env\b|\bgetenv\s*\("),
    # 直接引用敏感前缀变量（$ANTHROPIC_*, ${AWS_*}, $CLAUDE_* 等）
    re.compile(r"\$\{?(?:ANTHROPIC|AWS|CLAUDE)_[A-Za-z0-9_]*"),
)


def _is_env_access(command: str) -> bool:
    return any(p.search(command) for p in _PATTERNS)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0  # 读不到输入则放行，不阻断正常流程

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "") or ""

    if not _is_env_access(command):
        return 0

    audit(
        "env_access_blocked",
        {
            # 发起本次 agent 调用的用户（引擎经 KB_AGENT_AUDIT_USER 注入）
            "user": os.environ.get("KB_AGENT_AUDIT_USER") or "unknown",
            "session_id": payload.get("session_id"),
            "cwd": payload.get("cwd"),
            "command": command[:2000],
        },
    )
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": _DENY_REASON,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
