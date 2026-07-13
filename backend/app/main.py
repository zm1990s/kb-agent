"""KB-Agent FastAPI 应用入口。

启动时按配置幂等种子首个管理员；业务路由在 M1/M2/M3 挂载。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    admin,
    auth,
    categories,
    chat,
    documents,
    folders,
    settings,
    whatsnew,
    workspaces,
)
from app.core.db import SessionLocal
from app.core.logging_setup import configure_logging
from app.services.user_service import seed_admin
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
    yield


app = FastAPI(title="KB-Agent", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(categories.router)
app.include_router(folders.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(settings.router)
app.include_router(admin.router)
app.include_router(whatsnew.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
