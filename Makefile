.PHONY: dev down prod prod-down test lint

# 开发模式：源码 bind-mount，前端 HMR，改动立即生效
dev:
	docker compose up --build -d

# 停止并移除容器（开发模式）
down:
	docker compose down

# 生产模式：代码烤入镜像，前端编译优化。首次启动较慢（npm build ~1-2 min）
prod:
	docker compose -f docker-compose.prod.yml up --build -d

# 停止并移除容器（生产模式）
prod-down:
	docker compose -f docker-compose.prod.yml down

# 在 backend 容器内运行测试
test:
	docker compose run --rm backend pytest

# 在 backend 容器内跑 lint + 类型检查
lint:
	docker compose run --rm backend sh -c "ruff check . && pyright"
