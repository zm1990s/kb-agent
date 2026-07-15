# KB-Agent

面向内部员工与外部 Partner 的**共享 Agent 知识平台**：管理员上传文档 → Agent 自动归类/总结沉淀为可检索知识 → 用户通过对话查询知识并获取原文。架构预留 Skill 插拔框架（未来接入 SCM 等 skill，可在人工确认后下发 PANW 产品配置）。

## 已实现功能

- **认证/权限**：邮箱密码注册（域名白名单，DB 维护）、JWT 登录、管理员种子；**用户管理**（启禁用/重置密码/角色）、**用户组**（多维规则自动入组）、**RBAC**（组×模块×读写，admin 绕过）。
- **空间**：workspace 隔离；成员按个人 ∪ 用户组授权；空间可删除并打包下载全部文档。
- **文档**：批量/整目录上传（保持结构，单次最大 200 MB）、后台归类（Claude 读原文，支持 Bedrock）、目录树（拖拽移动/改层级/改名）、删除/移动/替换/重命名、全字段展示+自定义列+搜索、文件预览、处理日志与失败重试。
- **对话**：Agent 式两阶段索引问答（喂全空间索引，按需拉取原文）、SSE 流式工作阶段、气泡 UI + Markdown、多轮上下文、多会话历史、会话命名（AI 摘要 + 用户编辑 + Pin）、导航离开后恢复状态。
- **新动态**：定时摘要（daily/weekly/biweekly/monthly，可配提示词）、邮件订阅派发（SMTP）、前端展示卡片。
- **数据统计**：用量报表（按天/用户/动作聚合）、下载记录清单、对话记录清单、系统日志查看。
- **系统设置**：品牌配置（Logo/名称）、引擎选择（Claude CLI/占位）、**按任务模型配置**（归类/对话/新动态/会话标题各自独立选模型，DB 键 `model::classify` / `model::chat` / `model::whatsnew` / `model::title`）、提示词管理（版本历史/回退）、SMTP 配置、新动态定时配置。
- **前端**：Next.js 单端口入口，RBAC 菜单显隐；**5 语言国际化**（简体中文/繁体中文/English/日本語/한국어，NavBar 语言切换器，localStorage 持久化）；页面 = 新动态/对话/文档/空间管理/用户管理/系统设置/数据统计。

## 技术栈

- **Backend**: Python 3.12 + FastAPI（async）、Pydantic v2
- **Frontend**: Next.js 16.2.10 + React 19 + TypeScript + Tailwind CSS
- **数据库**: PostgreSQL 16（元数据 + 权限模型；对话用 Agent 式索引问答，不引入向量库）
- **文件存储**: 本地文件系统（经 `StorageProtocol` 抽象，未来可换云对象存储）
- **Agent 引擎**: 封装 Claude CLI 子进程（经 `EngineProtocol` 抽象；认证支持 API key/网关/AWS Bedrock；Codex/OpenClaw 预留灰显）
- **认证**: 自建用户表 + 邮箱密码，注册按域名后缀白名单
- **异步处理**: 归类走后台任务（处理任务表 + 日志 + 失败重试）
- **部署**: 云上部署（本地开发用 Docker Compose）

## 快速启动

前置：本机已安装 Docker，将仓库 clone 到本地后在根目录操作。

### 开发模式

源码 bind-mount 进容器，改动立即生效（前端 HMR）：

```bash
make dev          # 构建并启动（首次较慢）
make down         # 停止并移除容器
```

### 生产模式

代码烤入镜像，`next build` 在构建阶段完成，容器启动即可提供服务：

```bash
make prod         # 构建并启动（docker build 时执行 next build）
make prod-down    # 停止并移除容器
```

启动后访问（两种模式均相同）：

```bash
open http://localhost/          # 前端入口
open http://localhost/api/docs  # Swagger UI
docker compose logs -f frontend backend   # 查看日志（dev 模式）
```

### 其他命令

```bash
make test   # 在 backend 容器内运行 pytest
make lint   # 在 backend 容器内运行 ruff + pyright
```

> **单端口**：用户只访问 `:80`（Next.js），`/api/*` 由前端反代到后端，后端不对宿主暴露。
>
> **首次部署**：复制 `.env.example` 为 `.env`，修改 `JWT_SECRET` 及 Claude 凭据（API key 或 AWS Bedrock 环境变量）。归类与问答需容器内可访问 Claude CLI 且凭据已配置。

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
infra/postgres/  # init.sql（CREATE EXTENSION）+ migrations/（001…016，按序应用）
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
