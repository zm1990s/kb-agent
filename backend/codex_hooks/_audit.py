"""Hook 审计日志辅助（Codex CLI 版）。

与 claude_hooks/_audit.py 结构相同，路径指向同一 logs/ 目录。
"""

import datetime as _dt
import json
import os
from pathlib import Path

_LOG_DIR = os.environ.get("LOG_DIR", "/app/logs")
_VIOLATIONS_FILE = "security-violations.log"
_ACTIVITY_FILE = "hook-activity.log"


def _write(filename: str, record: dict) -> None:
    try:
        path = Path(_LOG_DIR) / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def audit(event: str, detail: dict) -> None:
    _write(_VIOLATIONS_FILE, {
        "ts": _dt.datetime.now(_dt.UTC).isoformat(),
        "event": event,
        **detail,
    })


def hook_log(hook: str, tool: str, verdict: str, detail: dict) -> None:
    _write(_ACTIVITY_FILE, {
        "ts": _dt.datetime.now(_dt.UTC).isoformat(),
        "hook": hook,
        "tool": tool,
        "verdict": verdict,
        **detail,
    })
