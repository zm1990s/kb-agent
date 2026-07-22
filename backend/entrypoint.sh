#!/bin/sh
# 以 root 启动，修复 bind-mount 目录权限后降权到 appuser 执行主进程。
# bind-mount 覆盖了镜像内的 chown，首次部署时目录 owner 是宿主 root。
set -e
chown -R appuser:appuser /app/local_storage /app/logs /app/codex_config 2>/dev/null || true

# 将内置 Codex Skills 合并到 CODEX_HOME/skills/（用户自定义优先，已存在的不覆盖）
if [ -d /app/codex_skills_builtin ] && [ "$(ls -A /app/codex_skills_builtin 2>/dev/null)" ]; then
    mkdir -p /app/codex_config/skills
    for skill_dir in /app/codex_skills_builtin/*/; do
        skill_name=$(basename "$skill_dir")
        dest="/app/codex_config/skills/$skill_name"
        if [ ! -d "$dest" ]; then
            cp -r "$skill_dir" "$dest"
        fi
    done
    chown -R appuser:appuser /app/codex_config/skills 2>/dev/null || true
fi

exec gosu appuser sh -c "python migrate.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"
