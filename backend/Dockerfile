FROM python:3.11-slim

WORKDIR /app

# 系统依赖：编译工具 + Node.js(Claude CLI) + poppler-utils(pdftotext 抽取 PDF)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates poppler-utils \
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

# 以非 root 用户运行：--dangerously-skip-permissions 拒绝 root；也是纵深防御。
# 家目录供 Claude CLI 写 ~/.claude 配置/缓存。
RUN useradd -m -u 10001 appuser \
    && mkdir -p /app/local_storage /app/logs \
    && chown -R appuser:appuser /app
USER appuser
ENV HOME=/home/appuser

EXPOSE 8000
# 启动时先跑增量迁移（幂等），再起 uvicorn
CMD ["sh", "-c", "python migrate.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
