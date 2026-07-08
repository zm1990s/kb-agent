"""KB-Agent FastAPI 应用入口。

启动时按配置幂等种子首个管理员；业务路由在 M1/M2/M3 挂载。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import (
    auth,
    categories,
    chat,
    documents,
    folders,
    settings,
    workspaces,
)
from app.core.db import SessionLocal
from app.services.user_service import seed_admin


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 幂等创建首个管理员（读 ADMIN_EMAIL/ADMIN_PASSWORD）
    async with SessionLocal() as session:
        await seed_admin(session)
    yield


app = FastAPI(title="KB-Agent", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(categories.router)
app.include_router(folders.router)
app.include_router(documents.router)
app.include_router(chat.router)
app.include_router(settings.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
