#!/usr/bin/env bash
# 运行后端测试。自带测试环境变量，不依赖 .env。
# 用法:
#   ./scripts/test.sh                # 跑全部测试
#   ./scripts/test.sh tests/test_m3_u4_chat.py   # 跑指定文件
#   ./scripts/test.sh -k chat -q     # 传任意 pytest 参数
set -euo pipefail
cd "$(dirname "$0")/.."

echo ">> 启动 postgres（若未运行）并等待就绪..."
docker compose up -d postgres >/dev/null
for i in $(seq 1 30); do
  s=$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q postgres)" 2>/dev/null || echo none)
  [ "$s" = "healthy" ] && break
  sleep 2
done
[ "$s" = "healthy" ] || { echo "postgres 未就绪 (status=$s)"; exit 1; }

echo ">> 运行 pytest..."
# CLAUDE_CLI_PATH=/bin/false：测试用假引擎，禁止真实调用 CLI 兜底
docker compose run --rm --no-deps \
  -e DATABASE_URL="postgresql+asyncpg://kbagent:kbagent@postgres:5432/kbagent" \
  -e JWT_SECRET="test-secret-not-for-prod" \
  -e LOCAL_STORAGE_DIR="/tmp/kbstore" \
  -e CLAUDE_CLI_PATH="/bin/false" \
  backend pytest "$@"
