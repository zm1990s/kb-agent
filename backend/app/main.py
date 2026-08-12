"""KB-Agent FastAPI 应用入口。

启动时按配置幂等种子首个管理员；业务路由在 M1/M2/M3 挂载。
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.api import (
    admin,
    admin_sso,
    auth,
    cases,
    categories,
    chat,
    documents,
    folders,
    icons,
    scheduled_tasks,
    settings,
    skills,
    sso,
    whatsnew,
    workspaces,
)
from app.core.db import SessionLocal, get_session
from app.core.logging_setup import configure_logging
from app.models.sso import SsoClient
from app.services.user_service import seed_admin
from app.tasks.chat_file_cleanup import start_chat_file_cleanup_loop
from app.tasks.scheduled_task_worker import start_scheduled_task_loop
from app.tasks.trash_cleanup import start_trash_cleanup_loop
from app.tasks.whatsnew_worker import start_mail_loop, start_whatsnew_loop

_bg_tasks: set = set()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    # 幂等创建首个管理员（读 ADMIN_EMAIL/ADMIN_PASSWORD）
    async with SessionLocal() as session:
        await seed_admin(session)
    import asyncio
    # 启动 What's New 定时摘要任务
    t1 = asyncio.create_task(start_whatsnew_loop())
    _bg_tasks.add(t1)
    t1.add_done_callback(_bg_tasks.discard)
    # 启动邮件订阅派发任务
    t2 = asyncio.create_task(start_mail_loop())
    _bg_tasks.add(t2)
    t2.add_done_callback(_bg_tasks.discard)
    # 启动回收站清理任务
    t3 = asyncio.create_task(start_trash_cleanup_loop())
    _bg_tasks.add(t3)
    t3.add_done_callback(_bg_tasks.discard)
    # 启动聊天+ 文件清理任务
    t4 = asyncio.create_task(start_chat_file_cleanup_loop())
    _bg_tasks.add(t4)
    t4.add_done_callback(_bg_tasks.discard)
    # 启动定时任务 Worker
    t5 = asyncio.create_task(start_scheduled_task_loop())
    _bg_tasks.add(t5)
    t5.add_done_callback(_bg_tasks.discard)
    yield


app = FastAPI(title="KB-Agent", version="0.1.0", lifespan=lifespan)

# SSO 专用 CORS：仅对 /sso/* 路径注入跨域头，不影响其他接口。
# 允许来源从 sso_clients 的 uri_prefix 派生（取 scheme+host 部分），30s TTL 缓存。
class _SsoCorsMiddleware(BaseHTTPMiddleware):
    _cache: set[str] = set()
    _cache_at: float = 0.0
    _TTL = 30.0

    async def _get_origins(self) -> set[str]:
        from sqlalchemy import select
        now = time.monotonic()
        if now - self._cache_at > self._TTL:
            try:
                async for session in get_session():
                    result = await session.execute(select(SsoClient.uri_prefix))
                    prefixes = [row for (row,) in result.all()]
                    self._cache = {
                        p.split("/")[0] + "//" + p.split("/")[2]
                        for p in prefixes
                        if len(p.split("/")) >= 3
                    }
                    self._cache_at = now
                    break
            except Exception:  # noqa: BLE001, S110
                pass  # 读取失败时沿用旧缓存，不影响正常请求
        return self._cache

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/sso/"):
            return await call_next(request)
        origin = request.headers.get("origin", "")
        if not origin:
            return await call_next(request)
        allowed = await self._get_origins()
        if origin not in allowed:
            return await call_next(request)
        if request.method == "OPTIONS":
            return Response(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Max-Age": "600",
                },
            )
        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        return response


app.add_middleware(_SsoCorsMiddleware)

app.include_router(auth.router)
app.include_router(sso.router)
app.include_router(admin_sso.router)
app.include_router(workspaces.router)
app.include_router(categories.router)
app.include_router(folders.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(whatsnew.router)
app.include_router(skills.router)
app.include_router(icons.router)
app.include_router(cases.router)
app.include_router(scheduled_tasks.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
