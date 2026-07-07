#!/usr/bin/env bash
# 跑 ruff + pyright（容器内，贴近真实运行环境）。
set -euo pipefail
cd "$(dirname "$0")/.."

echo ">> ruff..."
docker compose run --rm --no-deps backend ruff check .
echo ">> pyright..."
docker compose run --rm --no-deps backend pyright
echo ">> OK"
