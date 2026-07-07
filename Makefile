.PHONY: dev down test lint

# 启动本地依赖 + 后端（后台）
dev:
	docker compose up --build -d

# 停止并移除容器
down:
	docker compose down

# 在 backend 容器内运行测试
test:
	docker compose run --rm backend pytest

# 在 backend 容器内跑 lint + 类型检查
lint:
	docker compose run --rm backend sh -c "ruff check . && pyright"
