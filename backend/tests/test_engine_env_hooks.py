"""子进程 env 白名单 + Claude CLI PreToolUse hook（拦截 env 读取）。

覆盖：
- _build_cli_env 只透传认证/系统变量，剥离 JWT_SECRET/DATABASE_URL/SMTP_PASSWORD 等；
  audit_user 经 KB_AGENT_AUDIT_USER 注入
- _build_argv 放开工具时注入 --settings 指向 hook 配置
- pre_tool_use：env 读取命令被 deny，合法命令放行，审计记录用户名

注：CLI 2.1.197 不支持 PostToolUse updatedToolOutput（实测被忽略），故不做按值脱敏。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.engine.claude_cli import ClaudeCliEngine, _build_cli_env

_HOOK_DIR = Path(__file__).resolve().parent.parent / "claude_hooks"


# ── _build_cli_env ──────────────────────────────────────────
def test_build_cli_env_strips_app_secrets(monkeypatch):
    for k in list(__import__("os").environ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/app")
    monkeypatch.setenv("HOME", "/home/appuser")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "aws-secret")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    # 应被剥离的应用密钥
    monkeypatch.setenv("JWT_SECRET", "jwt-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("SMTP_PASSWORD", "smtp-secret")
    monkeypatch.setenv("ADMIN_PASSWORD", "admin-secret")

    env = _build_cli_env()

    # 透传认证 + 系统变量
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-secret"
    assert env["AWS_SECRET_ACCESS_KEY"] == "aws-secret"
    assert env["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert env["PATH"] == "/usr/bin:/app"
    assert env["HOME"] == "/home/appuser"
    # 剥离无关应用密钥
    assert "JWT_SECRET" not in env
    assert "DATABASE_URL" not in env
    assert "SMTP_PASSWORD" not in env
    assert "ADMIN_PASSWORD" not in env


def test_build_cli_env_prefix_covers_future_vars(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "gw-token")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gw.example")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "sess")
    env = _build_cli_env()
    assert env["ANTHROPIC_AUTH_TOKEN"] == "gw-token"
    assert env["ANTHROPIC_BASE_URL"] == "https://gw.example"
    assert env["AWS_SESSION_TOKEN"] == "sess"


def test_build_cli_env_injects_audit_user():
    assert "KB_AGENT_AUDIT_USER" not in _build_cli_env()
    env = _build_cli_env("bob@example.com")
    assert env["KB_AGENT_AUDIT_USER"] == "bob@example.com"


# ── --settings 注入 ─────────────────────────────────────────
def test_argv_injects_settings_when_tools_open():
    engine = ClaudeCliEngine()
    engine._hooks_settings = "/app/claude_hooks/settings.json"
    argv = engine._build_argv("总结", [Path("/app/local_storage/ws/a.pdf")])
    assert "--dangerously-skip-permissions" in argv
    assert "--settings" in argv
    assert argv[argv.index("--settings") + 1] == "/app/claude_hooks/settings.json"


def test_argv_no_settings_when_no_tools():
    engine = ClaudeCliEngine()
    engine._hooks_settings = "/app/claude_hooks/settings.json"
    argv = engine._build_argv("你好", None)
    assert "--settings" not in argv  # 未放开工具则无需 hook


def test_argv_no_settings_when_disabled():
    engine = ClaudeCliEngine()
    engine._hooks_settings = ""  # 配置留空 → 不注入
    argv = engine._build_argv("总结", None, cwd=Path("/tmp/wd"))
    assert "--dangerously-skip-permissions" in argv
    assert "--settings" not in argv


# ── hook 脚本执行 ───────────────────────────────────────────
def _run_hook(script: str, payload: dict, env: dict | None = None) -> str:
    p = subprocess.run(
        [sys.executable, str(_HOOK_DIR / script)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    assert p.returncode == 0, p.stderr
    return p.stdout


@pytest.mark.parametrize(
    "command",
    ["env", "printenv | grep AWS", "cat x; env", 'python3 -c "import os;print(os.environ)"'],
)
def test_pre_hook_denies_env_access(command, tmp_path):
    out = _run_hook(
        "pre_tool_use.py",
        {"tool_input": {"command": command}, "session_id": "t"},
        env={"LOG_DIR": str(tmp_path)},
    )
    decision = json.loads(out)["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "logged" in decision["permissionDecisionReason"].lower()


@pytest.mark.parametrize(
    "command",
    ["ls -la", "source venv/bin/activate", "python -m venv .venv", "docker run --env-file x"],
)
def test_pre_hook_allows_legit_commands(command, tmp_path):
    out = _run_hook(
        "pre_tool_use.py",
        {"tool_input": {"command": command}},
        env={"LOG_DIR": str(tmp_path)},
    )
    assert out.strip() == ""  # 空输出 = 放行


def test_pre_hook_audit_records_user_and_command(tmp_path):
    _run_hook(
        "pre_tool_use.py",
        {"tool_input": {"command": "env"}, "session_id": "sess-1"},
        env={"LOG_DIR": str(tmp_path), "KB_AGENT_AUDIT_USER": "alice@example.com"},
    )
    log = (tmp_path / "security-violations.log").read_text(encoding="utf-8")
    entry = json.loads(log.strip().splitlines()[-1])
    assert entry["event"] == "env_access_blocked"
    assert entry["user"] == "alice@example.com"
    assert entry["session_id"] == "sess-1"
    assert entry["command"] == "env"


def test_pre_hook_audit_user_defaults_unknown(tmp_path):
    _run_hook(
        "pre_tool_use.py",
        {"tool_input": {"command": "printenv"}},
        env={"LOG_DIR": str(tmp_path)},  # 未注入 KB_AGENT_AUDIT_USER
    )
    log = (tmp_path / "security-violations.log").read_text(encoding="utf-8")
    entry = json.loads(log.strip().splitlines()[-1])
    assert entry["user"] == "unknown"
