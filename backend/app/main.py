"""KB-Agent FastAPI 应用入口。

M0 阶段只提供健康检查；业务路由在 M1/M2/M3 挂载。
"""

from fastapi import FastAPI

from app.api import auth, categories, chat, documents, workspaces

app = FastAPI(title="KB-Agent", version="0.1.0")

app.include_router(auth.router)
app.include_router(workspaces.router)
app.include_router(categories.router)
app.include_router(documents.router)
app.include_router(chat.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
