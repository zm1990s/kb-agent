#!/usr/bin/env python3
"""PreToolUse hook：拦截读取/写入环境变量相关代码的操作。

覆盖工具：
  - Bash：命令字符串匹配 + 解释器执行脚本时读脚本内容 + 内联 -c 代码分析
  - Write / Edit / MultiEdit：写入内容含 env 读取模式时拒绝

命中时：
  1. 写安全审计日志；
  2. 输出 deny JSON（英文话术），reason 反馈给模型，模型会转告用户；
未命中则 exit 0 放行。
"""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "/app/claude_hooks")
from _audit import audit, hook_log  # noqa: E402

_DENY_REASON_ENV = (
    "Platform policy violation: reading environment variables is prohibited. "
    "This event has been logged. Please continue without accessing the "
    "environment; inform the user that this action was blocked and recorded."
)
_DENY_REASON_WRITE = (
    "Platform policy violation: writing code that reads environment variables "
    "is prohibited. This event has been logged. Please rewrite the content "
    "without environment variable access."
)
_DENY_REASON_PATH = (
    "Platform policy violation: file access outside the authorized workspace "
    "directory is prohibited. This event has been logged. Please only access "
    "files within the designated workspace; inform the user that this action "
    "was blocked and recorded."
)

# ── 环境变量读取模式 ──────────────────────────────────────────────────────────
_CMD_START = r"(?:^|[\n;&|]|\|\||&&|\bsudo\s+|\bnohup\s+|\bexec\s+)\s*"
_PATTERNS = (
    re.compile(_CMD_START + r"(?:env|printenv)(?:\s|$)"),
    re.compile(r"/proc/(?:self|\d+|\$\$|\$\{?[A-Za-z_]\w*\}?)/environ"),
    # Python
    re.compile(r"os\.environ\b|os\.environb\b|os\.getenv\s*\("),
    # Node.js
    re.compile(r"process\.env\b"),
    # C / generic getenv（同时覆盖 Lua os.getenv）
    re.compile(r"\bgetenv\s*\("),
    # Go: 大写 Getenv / Environ
    re.compile(r"\bos\.Getenv\s*\(|\bos\.Environ\s*\("),
    # dotenv 库
    re.compile(r"\bload_dotenv\s*\("),
    # Perl: %ENV hash 和 $ENV{KEY}
    re.compile(r"\%ENV\b|\$ENV\s*\{"),
    # Ruby: ENV[] / ENV.fetch / ENV.each
    re.compile(r"\bENV\s*[\[.]"),
    # AWK: ENVIRON 内置数组
    re.compile(r"\bENVIRON\b"),
    # PHP: $_ENV / $_SERVER（含 env 键）
    re.compile(r"\$_ENV\b|\$_SERVER\b"),
    # Tcl: $env(KEY) / array get env
    re.compile(r"\$env\s*\(|\barray\s+get\s+env\b"),
    # R: Sys.getenv()
    re.compile(r"\bSys\.getenv\s*\("),
    # PowerShell: $env:KEY / Get-ChildItem env: / GetEnvironmentVariables
    re.compile(r"\$env:|\bGet-ChildItem\s+env:|\bGetEnvironmentVariables\s*\("),
    # Shell builtins 枚举全量变量
    re.compile(_CMD_START + r"declare\s+-[pPxX]\b"),   # declare -p / -x
    re.compile(_CMD_START + r"compgen\s+-v\b"),         # compgen -v
    re.compile(_CMD_START + r"export\s+-[pP]\b"),       # export -p (print all)
    # jq env 内置函数（枚举全量 env）
    re.compile(_CMD_START + r"jq\b[^|;&\n]*\benv\b"),
    # 已知 AI / 云服务商变量前缀（按需追加即可）
    re.compile(
        r"\$\{?(?:"
        r"ANTHROPIC|CLAUDE|"          # Anthropic
        r"AWS|"                        # Amazon Web Services
        r"AZURE|"                      # Microsoft Azure
        r"OPENAI|"                     # OpenAI / Codex
        r"GOOGLE|GCP|GCLOUD|VERTEX|GEMINI|"  # Google Cloud / AI
        r"COHERE|"                     # Cohere
        r"HUGGINGFACE|HF_|"           # Hugging Face
        r"REPLICATE|"                  # Replicate
        r"TOGETHER|TOGETHERAI|"        # Together AI
        r"MISTRAL|"                    # Mistral
        r"GROQ|"                       # Groq
        r"DEEPSEEK|"                   # DeepSeek
        r"PERPLEXITY|"                 # Perplexity
        r"BEDROCK|SAGEMAKER"           # AWS AI services
        r")[A-Za-z0-9_]*"
    ),
    # 语义后缀兜底：任意前缀 + 敏感后缀——覆盖未来任何新服务商
    re.compile(
        r"\$\{?[A-Z][A-Z0-9_]*_"
        r"(?:API_KEY|SECRET_KEY|ACCESS_KEY|AUTH_TOKEN|API_TOKEN|"
        r"SECRET|PASSWORD|CREDENTIAL|PRIVATE_KEY|CLIENT_SECRET)"
        r"(?:\}|[^A-Z0-9_]|$)"
    ),
)

# ── 路径越界检查 ──────────────────────────────────────────────────────────────
# 从 Bash 命令中提取绝对路径的正则（覆盖常见数据和系统目录）
_ABS_PATH_RE = re.compile(
    r'(?<![/\w])/(?:data|etc|home|root|proc|var|tmp|app)/[^\s|;&><"\'\n]+'
)


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


# 脚本路径作为位置参数的解释器
_SCRIPT_INTERPRETERS = frozenset({
    "python", "python3", "node", "ruby", "perl",
    "bash", "sh", "zsh", "ksh", "fish",
    "lua", "luajit",
    "tclsh", "wish",
    "Rscript", "rscript",
    "pwsh", "powershell",
    "php",
    "groovy",
})
# 脚本路径通过 -f 传入的解释器
_SCRIPT_FLAG_INTERPRETERS = frozenset({"awk", "gawk", "nawk", "mawk"})


def _matches_pattern(text: str) -> bool:
    return any(p.search(text) for p in _PATTERNS)


def _extract_inline_code(command: str) -> str:
    """从 interpreter -c '...' 等内联执行中提取代码字符串。"""
    m = re.search(
        r"(?:python[23]?|node|bash|sh|zsh|ksh|fish|perl|ruby|lua|luajit|php|pwsh|powershell|tclsh|Rscript)\s+-[cCeErR](?:ommand)?\s+(['\"])(.*?)\1",
        command,
        re.DOTALL,
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
    """读取脚本文件内容检测 env 访问模式和越界路径。

    支持两种传参方式：
      - 位置参数：python/perl/bash/... script.py [args]
      - -f 参数：awk/gawk/... -f script.awk [args]
    """
    tokens = command.split()
    if not tokens:
        return False, ""
    interpreter = os.path.basename(tokens[0])

    # awk/gawk 等：脚本通过 -f 传入，或内联程序作为第一个引号包裹参数
    if interpreter in _SCRIPT_FLAG_INTERPRETERS:
        for i, tok in enumerate(tokens[1:], 1):
            if tok == "-f" and i + 1 < len(tokens):
                return _read_and_check(tokens[i + 1])
            if tok.startswith("-f") and len(tok) > 2:
                return _read_and_check(tok[2:])
        # awk 内联程序：用正则提取完整的引号字符串（split 会拆散引号内容）
        m = re.search(r"""(?:^|\s)awk\s+(?:[^'"\s]+\s+)*(['"'])(.*?)\1""", command, re.DOTALL)
        if not m:
            m = re.search(r"""awk\s+(['"'])(.*?)\1""", command, re.DOTALL)
        if m:
            if _matches_pattern(m.group(2)):
                return True, "env_read_in_executed_script"
        return False, ""

    # python/perl/bash 等：脚本是第一个非 - 参数
    if interpreter not in _SCRIPT_INTERPRETERS:
        return False, ""
    for tok in tokens[1:]:
        if tok.startswith("-"):
            continue
        return _read_and_check(tok)
    return False, ""


def _check_bash(tool_input: dict) -> tuple[bool, str]:
    """返回 (命中, 原因标签)。"""
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


def _check_write_content(content: str) -> tuple[bool, str]:
    """检查写入内容中的 env 访问模式和越界绝对路径。返回 (命中, 原因标签)。"""
    if _matches_pattern(content):
        return True, "env_read_pattern_in_written_content"
    allowed = _get_allowed_dirs()
    if allowed:
        for m in _ABS_PATH_RE.finditer(content):
            if not _path_allowed(m.group(0), allowed):
                return True, "file_path_outside_workspace_in_written_content"
    return False, ""


def _check_write(tool_input: dict) -> tuple[bool, str]:
    content = tool_input.get("content", "") or ""
    return _check_write_content(content)


def _check_edit(tool_input: dict) -> tuple[bool, str]:
    new_string = tool_input.get("new_string", "") or ""
    hit, label = _check_write_content(new_string)
    if hit:
        # 把 written_content 替换为 edited_content 以区分来源
        return True, label.replace("written_content", "edited_content")
    return False, ""


def _check_multiedit(tool_input: dict) -> tuple[bool, str]:
    for edit in tool_input.get("edits", []) or []:
        hit, label = _check_write_content(edit.get("new_string", "") or "")
        if hit:
            return True, label.replace("written_content", "multiedit_content")
    return False, ""


_PATH_REASON_LABELS = frozenset({
    "file_access_outside_workspace",
    "file_read_outside_workspace",
    "file_path_outside_workspace_in_written_content",
    "file_path_outside_workspace_in_edited_content",
    "file_path_outside_workspace_in_multiedit_content",
    "file_path_outside_workspace_in_executed_script",
})

_TOOL_CHECKERS = {
    "Bash": _check_bash,
    "Write": _check_write,
    "Edit": _check_edit,
    "MultiEdit": _check_multiedit,
    "Read": _check_read,
}

# 各工具命中时对应的拒绝话术（按 reason_label 区分 path 类 vs env 类）
def _deny_reason_for(tool_name: str, reason_label: str) -> str:
    if reason_label in _PATH_REASON_LABELS:
        return _DENY_REASON_PATH
    if tool_name in ("Write", "Edit", "MultiEdit"):
        return _DENY_REASON_WRITE
    return _DENY_REASON_ENV


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
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": deny_reason,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
