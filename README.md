# KB-Agent

面向内部员工与外部 Partner 的**共享 Agent 知识平台**：管理员上传文档 → Agent 自动归类/总结沉淀为可检索知识 → 用户通过对话查询知识并获取原文。架构预留 Skill 插拔框架（未来接入 SCM 等 skill，可在人工确认后下发 PANW 产品配置）。

## 技术栈

- **Backend**: Python 3.11 + FastAPI（async）、Pydantic v2
- **数据库**: PostgreSQL 16（元数据 + 全文检索 `tsvector`，MVP 不引入向量库）
- **文件存储**: MVP 本地文件系统（经 `StorageProtocol` 抽象，未来可换云对象存储）
- **Agent 引擎**: 封装 Claude CLI 子进程（经 `EngineProtocol` 抽象，预留 OpenClaw / Codex）
- **认证**: 自建用户表 + 邮箱密码，注册按域名后缀白名单
- **异步处理**: 归类走后台任务（处理任务表 + 日志 + 失败重试）
- **部署**: 云上部署（本地开发用 Docker Compose）

## 快速启动

前置：本机已安装 Docker。

```bash
# 运行测试（自带测试环境变量，无需 .env）
./scripts/test.sh                     # 全部
./scripts/test.sh tests/test_m3_u4_chat.py   # 指定文件
./scripts/test.sh -k chat             # 传任意 pytest 参数

# lint + 类型检查
./scripts/lint.sh

# 启动本地开发环境（首次自动生成 .env，起 postgres+backend，应用迁移）
./scripts/dev.sh
# 之后：
curl http://localhost:8000/health     # {"status":"ok"}
open http://localhost:8000/docs        # Swagger UI
docker compose logs -f backend         # 看日志
docker compose down                    # 停止
```

> **注意**：`.env` 存密钥，不入 git（已 gitignore）。`dev.sh` 首次会生成一份本地默认值，
> 请务必修改 `JWT_SECRET`，并把 `CLAUDE_CLI_PATH` 指向可用的 `claude` CLI（归类/问答需要）。
> 端到端跑通归类与问答，需容器内能访问 `claude` CLI 且已配置凭据。

## 目录说明

```
backend/app/
  api/        # 路由层：只做参数校验、鉴权、转发
  services/   # 业务逻辑，单一职责
  models/     # SQLAlchemy ORM 模型
  schemas/    # Pydantic 请求/响应 schema
  core/       # 配置、DB 连接、鉴权中间件
  engine/     # 【唯一 LLM 出口】EngineProtocol + ClaudeCliEngine
  skills/     # 【预留】skill 插拔框架
  storage/    # StorageProtocol + LocalStorage
  tasks/      # 后台任务：归类 worker、任务状态与重试
infra/postgres/  # init.sql（按 DESIGN.md 建表）
docs/            # PRD / DESIGN / ROADMAP / WORKFLOW / SECURITY
prompts/         # 分步实现提示词
```

## 文档

- 需求：[docs/PRD.md](docs/PRD.md)
- 架构与契约：[DESIGN.md](DESIGN.md)、[CLAUDE.md](CLAUDE.md)
- 实现路径：[docs/ROADMAP.md](docs/ROADMAP.md)
- 开发协议：[WORKFLOW.md](WORKFLOW.md)
- 安全威胁模型：[docs/SECURITY.md](docs/SECURITY.md)

## 开发约定（摘要，详见 CLAUDE.md）

- 所有 LLM 调用只经 `app/engine/`，文件存取只经 `app/storage/`
- 所有文档查询强制带 workspace 权限过滤（防越权/IDOR）
- 密钥不硬编码；`storage_key` 服务端生成，防路径穿越
- 每个 Unit 改动 ≤200 行，配测试，lint + 类型检查通过
