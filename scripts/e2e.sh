#!/usr/bin/env bash
# 前端 e2e 冒烟（Playwright）。需先 ./scripts/dev.sh 起栈。
# Alpine 无法跑 Playwright chromium（musl），故用官方 Playwright 镜像在 compose 网络内跑，
# 目标为 frontend 服务（单端口）。
set -euo pipefail
cd "$(dirname "$0")/.."

NET=$(docker network ls --format '{{.Name}}' | grep kb-agent | head -1)
[ -n "$NET" ] || { echo "未找到 compose 网络，请先 ./scripts/dev.sh"; exit 1; }

echo ">> 在 $NET 网络内运行 Playwright 冒烟（目标 http://frontend:80）..."
docker run --rm --network "$NET" \
  -e E2E_BASE_URL=http://frontend:80 \
  -v "$PWD/frontend:/work" -w /work \
  mcr.microsoft.com/playwright:v1.45.3-jammy \
  sh -c "npm install -D @playwright/test@1.45.3 >/dev/null 2>&1 && npx playwright test"
