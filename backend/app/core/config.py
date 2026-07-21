"""应用配置：全部从环境变量 / .env 读取，禁止硬编码密钥。"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── 数据库 ──────────────────────────────────────────
    database_url: str = Field(..., alias="DATABASE_URL")

    # ── 认证 ───────────────────────────────────────────
    jwt_secret: str = Field(..., alias="JWT_SECRET")
    jwt_expire_min: int = Field(60, alias="JWT_EXPIRE_MIN")
    # 注：注册域名白名单已迁到 DB（allowed_domains 表），由管理员在应用内维护。

    # 首个管理员种子（启动时幂等创建）。留空则不种子。
    admin_email: str = Field("", alias="ADMIN_EMAIL")
    admin_password: str = Field("", alias="ADMIN_PASSWORD")

    # ── Agent 引擎（唯一 LLM 出口）────────────────────────
    engine_backend: str = Field("claude_cli", alias="ENGINE_BACKEND")
    claude_cli_path: str = Field("claude", alias="CLAUDE_CLI_PATH")
    claude_model: str = Field("", alias="CLAUDE_MODEL")
    engine_idle_timeout_sec: int = Field(300, alias="ENGINE_IDLE_TIMEOUT_SEC")
    # 子进程 stdout 单行缓冲上限（字节）。stream-json 每行一个 JSON 事件，
    # 大文件工具结果/整条消息快照可能超 asyncio 默认 64KB → LimitOverrunError。
    engine_stream_limit_bytes: int = Field(
        16 * 1024 * 1024, alias="ENGINE_STREAM_LIMIT_BYTES"
    )
    # Claude CLI hook 配置文件（PreToolUse/PostToolUse 拦截 env 读取 + 脱敏）。
    # 经 --settings 注入；留空则不注入 hook（仅测试/特殊场景）。
    claude_hooks_settings: str = Field(
        "/app/claude_hooks/settings.json", alias="CLAUDE_HOOKS_SETTINGS"
    )

    # Codex CLI 引擎配置
    codex_cli_path: str = Field("codex", alias="CODEX_CLI_PATH")
    # CODEX_HOME：挂载的配置目录（含 config.toml / hooks.json）
    codex_config_dir: str = Field("/app/codex_config", alias="CODEX_CONFIG_DIR")

    # ── 上传限制 ────────────────────────────────────────
    max_upload_mb: int = Field(200, alias="MAX_UPLOAD_MB")

    # ── 存储（MVP 本地文件系统）──────────────────────────
    storage_backend: str = Field("local", alias="STORAGE_BACKEND")
    local_storage_dir: str = Field("./local_storage", alias="LOCAL_STORAGE_DIR")
    download_url_ttl_sec: int = Field(300, alias="DOWNLOAD_URL_TTL_SEC")

    # ── 邮件（SMTP）──────────────────────────────────────
    smtp_host: str = Field("", alias="SMTP_HOST")
    smtp_port: int = Field(587, alias="SMTP_PORT")
    smtp_user: str = Field("", alias="SMTP_USER")
    smtp_password: str = Field("", alias="SMTP_PASSWORD")
    smtp_from: str = Field("", alias="SMTP_FROM")
    smtp_tls: bool = Field(True, alias="SMTP_TLS")

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 值来自环境变量
