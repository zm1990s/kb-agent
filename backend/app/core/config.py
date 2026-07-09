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
    engine_idle_timeout_sec: int = Field(60, alias="ENGINE_IDLE_TIMEOUT_SEC")

    # ── 存储（MVP 本地文件系统）──────────────────────────
    storage_backend: str = Field("local", alias="STORAGE_BACKEND")
    local_storage_dir: str = Field("./local_storage", alias="LOCAL_STORAGE_DIR")
    download_url_ttl_sec: int = Field(300, alias="DOWNLOAD_URL_TTL_SEC")

@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 值来自环境变量
