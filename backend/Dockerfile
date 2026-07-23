FROM python:3.12-slim

WORKDIR /app

# 系统依赖：编译工具 + Node.js(Claude CLI) + poppler-utils(pdftotext 抽取 PDF)
# 注：Case 录入导出中文 PDF 用 reportlab 内置 CID 字体(STSong-Light)，无需额外字体包
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl ca-certificates poppler-utils gosu fontconfig unzip \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI（归类/问答的 LLM 引擎；认证凭据在运行时经环境变量注入）
RUN npm install -g @anthropic-ai/claude-code

# OpenAI Codex CLI（可选对话引擎；认证凭据在运行时经 OPENAI_API_KEY 注入）
RUN npm install -g @openai/codex

# @oai/artifact-tool（私有包，无法从 npm 公有源安装；从本地 vendor 拷入全局 node_modules）
# skia-canvas 内含 macOS native binding，需重新下载 Linux 版（从 GitHub public releases）。
COPY vendor/@oai /usr/local/lib/node_modules/@oai
# 删除 macOS native binding（vendor 从 macOS 开发机拷入），强制 download Linux 版
RUN rm -f /usr/local/lib/node_modules/@oai/artifact-tool/node_modules/skia-canvas/lib/skia.node \
    && node /usr/local/lib/node_modules/@oai/artifact-tool/node_modules/skia-canvas/lib/prebuild.mjs download

# 先装依赖以利用层缓存
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir ".[dev]"

# Codex CLI 运行时工具（供 codex exec 子进程调用）
RUN pip install --no-cache-dir python-pptx markitdown pdf2image

COPY . .

# 内置 Codex Skills（烧录进镜像；entrypoint 启动时合并到 CODEX_HOME/skills/）
# 放在不被 bind-mount 覆盖的独立路径，用户在 data/codex/skills/ 添加的自定义 skill 优先。
RUN if [ -d codex_skills ] && [ "$(ls -A codex_skills 2>/dev/null)" ]; then \
        cp -r codex_skills /app/codex_skills_builtin; \
    else \
        mkdir -p /app/codex_skills_builtin; \
    fi

# 以非 root 用户运行：--dangerously-skip-permissions 拒绝 root；也是纵深防御。
# 家目录供 Claude CLI 写 ~/.claude 配置/缓存。
RUN useradd -m -u 10001 appuser \
    && mkdir -p /app/local_storage /app/logs \
    && chown -R appuser:appuser /app

# 预置内置 Skill（Claude CLI 原生机制）：启动即自动发现，无需注入提示词。
# /home/appuser 不被 bind-mount 覆盖，故装在此处对每次 CLI 调用生效。
RUN mkdir -p /home/appuser/.claude/skills \
    && cp -r /app/claude_skills/. /home/appuser/.claude/skills/ \
    && chown -R appuser:appuser /home/appuser/.claude
# entrypoint 以 root 启动，修复 bind-mount 目录权限后用 gosu 降权到 appuser
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENV HOME=/home/appuser

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
