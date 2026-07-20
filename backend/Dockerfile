FROM python:3.12-slim

WORKDIR /app

# 系统依赖：编译工具 + Node.js(Claude CLI) + poppler-utils(pdftotext 抽取 PDF)
# 注：Case 录入导出中文 PDF 用 reportlab 内置 CID 字体(STSong-Light)，无需额外字体包
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates poppler-utils gosu \
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

# 预置内置 Skill（Claude CLI 原生机制）：启动即自动发现，无需注入提示词。
# /home/appuser 不被 bind-mount 覆盖，故装在此处对每次 CLI 调用生效。
RUN mkdir -p /home/appuser/.claude/skills \
    && cp -r /app/skills/. /home/appuser/.claude/skills/ \
    && chown -R appuser:appuser /home/appuser/.claude
# entrypoint 以 root 启动，修复 bind-mount 目录权限后用 gosu 降权到 appuser
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV HOME=/home/appuser

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
