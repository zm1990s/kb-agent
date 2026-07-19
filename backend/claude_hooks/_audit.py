"""Hook 审计日志辅助。

hook 脚本运行在 claude 子进程里，其环境已被 claude_cli._build_cli_env 剥离
DATABASE_URL，无法连库——故审计走本地文件，与应用 logs/ 体系一致。

两个日志文件：
  security-violations.log  — 违规拦截与敏感值命中（已有）
  hook-activity.log        — 每次 hook 调用的详细检测过程，用于排查误判/漏判
"""

import datetime as _dt
import json
import os
from pathlib import Path

# 与应用日志同目录（Dockerfile 设 LOG_DIR=/app/logs 并 chown appuser）。
_LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
_VIOLATIONS_FILE = "security-violations.log"
_ACTIVITY_FILE = "hook-activity.log"


def _write(filename: str, record: dict) -> None:
    try:
        path = Path(_LOG_DIR) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001, S110
        pass


def audit(event: str, detail: dict) -> None:
    """追加一条安全违规记录（JSON 行）。失败静默——绝不因日志问题影响主流程。"""
    _write(_VIOLATIONS_FILE, {
        "ts": _dt.datetime.now(_dt.UTC).isoformat(),
        "event": event,
        **detail,
    })


def hook_log(hook: str, tool: str, verdict: str, detail: dict) -> None:
    """记录一次 hook 检测过程到 hook-activity.log。

    hook:    "pre" | "post"
    tool:    工具名，如 "Bash" / "Write"
    verdict: "allow" | "deny" | "redact" | "audit"
    detail:  任意附加字段（command 截断、file_path、reason 等）
    """
    _write(_ACTIVITY_FILE, {
        "ts": _dt.datetime.now(_dt.UTC).isoformat(),
        "hook": hook,
        "tool": tool,
        "verdict": verdict,
        **detail,
    })
