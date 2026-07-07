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
    # 注册域名白名单，逗号分隔。完整域名相等匹配（不使用 endswith）。
    allowed_email_domains: str = Field("", alias="ALLOWED_EMAIL_DOMAINS")

    # ── Agent 引擎（唯一 LLM 出口）────────────────────────
    engine_backend: str = Field("claude_cli", alias="ENGINE_BACKEND")
    claude_cli_path: str = Field("claude", alias="CLAUDE_CLI_PATH")
    claude_model: str = Field("", alias="CLAUDE_MODEL")
    engine_timeout_sec: int = Field(120, alias="ENGINE_TIMEOUT_SEC")

    # ── 存储（MVP 本地文件系统）──────────────────────────
    storage_backend: str = Field("local", alias="STORAGE_BACKEND")
    local_storage_dir: str = Field("./local_storage", alias="LOCAL_STORAGE_DIR")
    download_url_ttl_sec: int = Field(300, alias="DOWNLOAD_URL_TTL_SEC")

    @property
    def allowed_email_domains_set(self) -> set[str]:
        """解析为小写域名集合，供注册白名单精确匹配使用。"""
        return {
            d.strip().lower()
            for d in self.allowed_email_domains.split(",")
            if d.strip()
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # 值来自环境变量
