"""应用日志配置：控制台 + 轮询文件（10MB × 最多 10 个文件）。"""

import logging
import os
from logging.handlers import RotatingFileHandler

LOG_DIR = os.environ.get("LOG_DIR", "./logs")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

_configured = False


def configure_logging() -> None:
    global _configured
    if _configured:
        return
    _configured = True

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(LOG_LEVEL)

    # 控制台
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    root.addHandler(ch)

    os.makedirs(LOG_DIR, exist_ok=True)

    # 应用日志（业务逻辑、任务、错误等）
    fh = RotatingFileHandler(
        os.path.join(LOG_DIR, "kb-agent.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # 访问日志（uvicorn HTTP 请求记录）
    access_fh = RotatingFileHandler(
        os.path.join(LOG_DIR, "access.log"),
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    access_fh.setFormatter(fmt)
    logging.getLogger("uvicorn.access").addHandler(access_fh)
    logging.getLogger("uvicorn.error").addHandler(access_fh)

    # 降低 sqlalchemy 噪声
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_log_dir() -> str:
    return LOG_DIR
