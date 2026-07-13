#!/bin/sh
# 以 root 启动，修复 bind-mount 目录权限后降权到 appuser 执行主进程。
# bind-mount 覆盖了镜像内的 chown，首次部署时目录 owner 是宿主 root。
set -e
chown -R appuser:appuser /app/local_storage /app/logs 2>/dev/null || true
exec gosu appuser sh -c "python migrate.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"
