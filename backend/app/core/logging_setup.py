"""应用日志配置：控制台 + 轮询文件（10MB × 最多 10 个文件）。

注意：uvicorn 启动时会初始化自己的 logger，并将 propagate 设为 False，
导致后续通过 root logger 添加的文件 handler 无法捕获 uvicorn 日志。
解决方案：在 configure_logging() 中直接把文件 handler 加到 uvicorn 的 logger 上，
并强制 propagate=True，确保 uvicorn 日志也写入 kb-agent.log。
"""

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

    # 控制台（避免重复添加，如 reload 模式下可能被调用多次）
    if not any(isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
               for h in root.handlers):
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        root.addHandler(ch)

    os.makedirs(LOG_DIR, exist_ok=True)

    # 应用日志（业务逻辑、任务、uvicorn 启停等）
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

    # uvicorn 默认 propagate=False，需手动把 handler 加到它的 logger 上，
    # 同时开启 propagate 让 root handler（kb-agent.log）也能捕获 uvicorn 日志。
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.propagate = True
        uv_logger.setLevel(logging.INFO)

    # access.log 专门挂到 uvicorn.access 上
    logging.getLogger("uvicorn.access").addHandler(access_fh)

    # 降低 sqlalchemy 噪声
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_log_dir() -> str:
    return LOG_DIR
