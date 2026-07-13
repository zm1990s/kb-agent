# KB-Agent

面向内部员工与外部 Partner 的**共享 Agent 知识平台**：管理员上传文档 → Agent 自动归类/总结沉淀为可检索知识 → 用户通过对话查询知识并获取原文。架构预留 Skill 插拔框架（未来接入 SCM 等 skill，可在人工确认后下发 PANW 产品配置）。

## 已实现功能

- **认证/权限**：邮箱密码注册（域名白名单，DB 维护）、JWT 登录、管理员种子；**用户管理**（启禁用/重置密码/角色）、**用户组**（多维规则自动入组）、**RBAC**（组×模块×读写，admin 绕过）。
- **空间**：workspace 隔离；成员按个人 ∪ 用户组授权；空间可删除并打包下载全部文档。
- **文档**：批量/整目录上传（保持结构）、后台归类（Claude 读原文，支持 Bedrock）、目录树（拖拽移动/改层级/改名）、删除/移动/替换、全字段展示+自定义列+搜索、文件预览、处理日志与失败重试。
- **对话**：Agent 式两阶段索引问答（喂全空间索引，按需拉取原文）、SSE 流式工作阶段、气泡 UI + Markdown、多轮上下文、多会话历史、会话命名（AI 摘要 + 用户编辑 + Pin）、导航离开后恢复状态。
- **新动态**：定时摘要（daily/weekly/biweekly/monthly，可配提示词）、邮件订阅派发（SMTP）、前端展示卡片。
- **数据统计**：用量报表（按天/用户/动作聚合）、下载记录清单、对话记录清单、系统日志查看。
- **系统设置**：品牌配置（Logo/名称）、引擎选择（Claude CLI/占位）、提示词管理（版本历史/回退）、SMTP 配置、新动态定时配置。
- **前端**：Next.js 单端口入口，RBAC 菜单显隐；页面 = 新动态/对话/文档/空间管理/用户管理/系统设置/数据统计。

## 技术栈

- **Backend**: Python 3.12 + FastAPI（async）、Pydantic v2
- **数据库**: PostgreSQL 16（元数据 + 权限模型；对话用 Agent 式索引问答，不引入向量库）
- **文件存储**: 本地文件系统（经 `StorageProtocol` 抽象，未来可换云对象存储）
- **Agent 引擎**: 封装 Claude CLI 子进程（经 `EngineProtocol` 抽象；认证支持 API key/网关/AWS Bedrock；Codex/OpenClaw 预留灰显）
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

# 启动本地开发环境（前端+后端+DB，单端口入口，应用迁移）
./scripts/dev.sh
# 之后（用户只访问一个端口 :80）：
open http://localhost/                 # 前端（登录/对话/文档/管理）
curl http://localhost/api/health       # {"status":"ok"}（经前端反代到后端）
open http://localhost/api/docs          # Swagger UI
docker compose logs -f frontend backend # 看日志
docker compose down                     # 停止

# 前端 e2e 冒烟（需先起栈）
./scripts/e2e.sh
```

> **单端口**：用户只访问 `:80`（Next.js），后端不对宿主暴露，`/api/*` 由前端反代。
>
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
