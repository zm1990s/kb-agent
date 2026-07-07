#!/usr/bin/env bash
# 启动本地开发环境：生成 .env（若缺）、起 postgres+backend、应用迁移。
# 访问: http://localhost:8000/health  |  http://localhost:8000/docs
set -euo pipefail
cd "$(dirname "$0")/.."

# 1) 生成本地 .env（仅本地开发默认值；已被 .gitignore 忽略）
if [ ! -f .env ]; then
  echo ">> 生成 .env（本地默认值，请按需修改，尤其 CLAUDE_CLI_PATH / JWT_SECRET）"
  cat > .env <<'EOF'
DATABASE_URL=postgresql+asyncpg://kbagent:kbagent@postgres:5432/kbagent
JWT_SECRET=dev-only-change-me
JWT_EXPIRE_MIN=60
ALLOWED_EMAIL_DOMAINS=company.com
ADMIN_EMAIL=admin@company.com
ADMIN_PASSWORD=ChangeMe_Admin123
ENGINE_BACKEND=claude_cli
CLAUDE_CLI_PATH=claude
CLAUDE_MODEL=
ENGINE_TIMEOUT_SEC=120
STORAGE_BACKEND=local
LOCAL_STORAGE_DIR=/app/local_storage
DOWNLOAD_URL_TTL_SEC=300
EOF
else
  echo ">> 已存在 .env，跳过生成"
fi

# 2) 起服务
echo ">> docker compose up -d --build"
docker compose up -d --build

# 3) 等 postgres 就绪
echo ">> 等待 postgres 就绪..."
for i in $(seq 1 30); do
  s=$(docker inspect --format '{{.State.Health.Status}}' "$(docker compose ps -q postgres)" 2>/dev/null || echo none)
  [ "$s" = "healthy" ] && break
  sleep 2
done
[ "$s" = "healthy" ] || { echo "postgres 未就绪 (status=$s)"; exit 1; }

# 4) 应用迁移（幂等）
echo ">> 应用数据库迁移..."
for f in infra/postgres/migrations/*.sql; do
  echo "   - $f"
  docker compose exec -T postgres psql -U kbagent -d kbagent -q -v ON_ERROR_STOP=1 < "$f"
done

echo ""
echo ">> 就绪（单端口入口，用户只访问 :80）。"
echo "   前端:     http://localhost/"
echo "   健康检查: curl http://localhost/api/health   # 经前端反代到后端"
echo "   API 文档: http://localhost/api/docs"
echo "   查看日志: docker compose logs -f frontend backend"
echo "   停止:     docker compose down"
