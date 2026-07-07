基于 CLAUDE.md 的目录约定和 DESIGN.md 的数据模型，生成项目骨架（M0 模块）。

先列完整目录树让我确认，再生成关键文件：
- docker-compose.yml：postgres:16、backend 服务（**不用 MinIO，文件存本地目录并挂载 volume**）
- backend/Dockerfile + pyproject.toml（fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, pydantic, pydantic-settings, python-jose, passlib[bcrypt], pytest, ruff, pyright）
- backend/app/core/config.py：pydantic-settings 读 .env（含 ALLOWED_EMAIL_DOMAINS、LOCAL_STORAGE_DIR 等）
- backend/app/core/db.py：async engine + session 依赖
- backend/app/main.py：FastAPI app + GET /health
- backend/app/engine/base.py：EngineProtocol + EngineResult + get_engine() 工厂
- backend/app/engine/claude_cli.py：ClaudeCliEngine（子进程调 claude，含超时/错误处理）
- backend/app/storage/base.py：StorageProtocol + get_storage() 工厂
- backend/app/storage/local.py：LocalStorage（save/open_path/download_url，本地目录）
- infra/postgres/init.sql：先留空或仅 CREATE EXTENSION（表交给 M1/M2）
- Makefile：dev / down / test / lint

严格约束：
- 不写任何业务逻辑（不建 users/documents 等表，不写路由业务）
- 所有 LLM 调用只经 engine/，业务层不得直连
- 所有文件存取只经 storage/，业务层不得直接拼路径读写
完成后跑：
  docker compose config >/dev/null && echo "compose 合法"
  find backend -maxdepth 3 -type f
  cd backend && ruff check . && echo "lint ok"
