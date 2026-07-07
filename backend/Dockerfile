FROM python:3.11-slim

WORKDIR /app

# 系统依赖（asyncpg/bcrypt 编译所需的基础工具 + Node.js 供 Claude Code CLI）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI（归类/问答的 LLM 引擎；认证凭据在运行时经环境变量注入）
RUN npm install -g @anthropic-ai/claude-code

# 先装依赖以利用层缓存
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[dev]"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
