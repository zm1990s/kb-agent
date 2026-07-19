# KB-Agent

> 面向内部员工与外部 Partner 的**共享 Agent 知识平台**：管理员上传文档 → Agent 自动归类/总结沉淀为可检索知识 → 用户通过对话查询知识并获取原文；支持 Skill 库与聊天+工作台，让 Agent 完成更复杂的生成任务。

---

## 使用场景

**知识沉淀与检索**：将产品手册、技术文档、FAQ 批量上传，Agent 自动归类整理并建立全文索引，员工通过对话即可获取答案和原文下载链接，无需手动翻阅文件夹。

**多人协作与权限隔离**：通过空间隔离和用户组授权，将不同级别的知识开放给不同人员，各方只能访问被授权的内容，适合内外部协作场景。

**聊天+工作台**（v2.0）：选择 Skill 定义 Agent 行为，上传附件或引用知识库原文，让 Agent 完成文档生成、数据整理等复杂任务，成果文件可直接下载；交互模式支持 AI 主动向用户提问，实现引导式 AI 规划与学习等场景。

**Skill 共享复用**（v2.0）：将常用提示词和附属文件封装为 Skill，统一保存到 Skill 库，团队成员按权限共享使用，平台内置 Claude 官方 Skill 开箱即用。

---

## 功能介绍

### v1.0 · 知识库平台

- **空间管理**：支持创建多个独立空间，不同空间之间完全隔离，适合按业务线、密级或团队分类存放文档。
- **知识库索引**：上传任意格式文档（Word / PDF / 图片 / Excel / PPT 等），AI 自动识别内容（含图片文字）、生成摘要与标签，并建立全文检索索引。
- **文档查询**：支持目录树浏览（传统方式）和 AI 对话问询两种方式；AI 回答会自动附上相关文档的原文下载链接，方便核查原始资料。
- **新动态订阅**：系统自动追踪平台内的文档变化并定期汇总，订阅的用户可通过邮件定期收到知识动态通知。
- **灵活引擎接入**：文件索引任务使用 Claude 完成；对话任务可选 Claude 或任意 OpenAI Compatible API 兼容模型。

### v2.0 · 聊天+与 Skill 库

- **聊天+工作台**：相当于将 Claude 桌面端能力内嵌到平台中，用户可上传任意文件、引用知识库文档，让 Agent 完成任意生成与处理任务，成果文件可在工作台直接下载。
- **Skill 管理**：用户可手动上传或借助 AI 生成 Skill（SKILL.md 格式），一键保存到平台 Skill 库。多人可协同使用同一 Skill 库，管理员控制可见范围；平台内置 Claude 官方 Skill 供直接使用。
- **交互模式**：模拟 Claude 桌面端的 ask-user 交互，AI 在对话中会主动弹出问题框让用户选择。结合 Skill 可实现 AI 引导学习、AI 辅助规划等互动场景。

### 平台基础

- **多用户管理**：管理员设置域名白名单，用户通过企业邮箱自助注册；支持用户组与 RBAC 权限模型，按模块精细授权。
- **完整审计记录**：管理员可查看用户的文件下载、对话记录等完整使用情况，满足企业合规要求。

---

## 功能概览

### 核心能力

| 模块 | 功能 |
|------|------|
| **认证 & 权限** | 邮箱密码注册（域名白名单）、JWT、用户组 RBAC（9 模块 × 读写）、admin 绕过、自助找回密码 |
| **空间隔离** | Workspace 隔离边界；成员按个人或用户组授权；空间可删除并打包下载 |
| **文档管理** | 批量/目录上传（≤200 MB）、Claude 后台归类、目录树拖拽、回收站（30 天软删除）、文件预览 |
| **对话查询** | Agent 式两阶段索引问答、SSE 流式推送、多轮上下文、会话 Pin & 命名、thinking 过程可折叠查看 |
| **聊天+**（v2.0） | 独立工作台，Skill 注入系统提示、附件上传/下载、文档引用、后台生成任务、交互模式（ask-user 协议） |
| **Skill 库**（v2.0） | 平台级/空间级 Skill，可见性控制、用户组权限、Bundle 打包、操作审计日志 |
| **新动态** | 定时知识摘要（daily–monthly）、邮件订阅派发、前端卡片展示 |
| **数据统计** | 用量报表、下载记录、对话记录、系统日志 |
| **系统设置** | 品牌配置、AI 引擎选择、按任务模型配置、提示词版本管理、SMTP、国际化（5 语言） |

---

## 技术栈

| 层 | 技术 |
|----|------|
| Backend | Python 3.12 + FastAPI (async)、Pydantic v2 |
| Frontend | Next.js 16.2.10 + React 19 + TypeScript + Tailwind CSS |
| 数据库 | PostgreSQL 16（全文检索 tsvector + GIN 索引，不引入向量库） |
| Agent 引擎 | 封装 Claude CLI 子进程（EngineProtocol 抽象；支持 API key / 网关 / AWS Bedrock） |
| 文件存储 | 本地文件系统（StorageProtocol 抽象，可换云对象存储） |
| 部署 | Docker Compose（开发 / 生产双模式） |

---

## 前置条件

### 0. 云主机与 Claude Key

- **海外云主机**：Claude CLI 需要访问 Anthropic API，建议部署在海外云主机（如 AWS、GCP、Azure 海外区域）或网络可达 Anthropic 服务的环境。
- **Claude 模型 Key**：需要以下任意一种来源的 Claude 模型访问凭据：
  - Anthropic 官方 API key（[console.anthropic.com](https://console.anthropic.com)）
  - AWS Bedrock（需开通 Claude 模型权限）
  - Azure 或其他兼容网关（通过 `ANTHROPIC_BASE_URL` 配置）

### 1. 安装 Docker

本项目通过 Docker Compose 运行，需提前安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（含 Compose 插件）。

### 2. 配置环境变量

```bash
cp .env.example .env
```

下表列出各变量含义及默认值：

#### 数据库

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接串（asyncpg 驱动） | `postgresql+asyncpg://kbagent:kbagent@postgres:5432/kbagent` |

#### 认证

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `JWT_SECRET` | JWT 签名密钥，**生产必须改为随机长字符串** | 无（必填） |
| `JWT_EXPIRE_MIN` | Token 有效期（分钟） | `60` |
| `ADMIN_EMAIL` | 首个管理员邮箱，留空则不创建 | 无 |
| `ADMIN_PASSWORD` | 首个管理员密码，**生产务必用强密码** | 无 |

#### Agent 引擎

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENGINE_BACKEND` | 引擎类型，当前支持 `claude_cli` | `claude_cli` |
| `CLAUDE_CLI_PATH` | Claude CLI 可执行路径 | `claude` |
| `CLAUDE_MODEL` | 指定模型（留空使用 CLI 默认） | 无 |
| `ENGINE_IDLE_TIMEOUT_SEC` | 空闲超时秒数（连续无输出才计时，非总时长） | `300` |

Claude CLI 认证方式三选一，其余留空：

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_API_KEY` | 方式一：Anthropic 官方 API key |
| `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` | 方式二：自定义网关（如 Portkey） |
| `CLAUDE_CODE_USE_BEDROCK` + `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` + `AWS_SESSION_TOKEN` + `AWS_REGION` | 方式三：AWS Bedrock |

#### 文件存储

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `STORAGE_BACKEND` | 存储后端，当前支持 `local` | `local` |
| `LOCAL_STORAGE_DIR` | 本地存储目录（容器内路径） | 无（必填） |
| `DOWNLOAD_URL_TTL_SEC` | 下载链接有效期（秒） | `3600` |

#### 邮件通知（SMTP）

SMTP 配置支持两种方式：

- **系统设置 UI**（推荐）：部署后在「系统设置 → SMTP 邮件」中填写，无需重启，DB 优先级高于 env。
- **环境变量**：作为初始默认值，适合首次部署时预填。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `SMTP_HOST` | SMTP 服务器地址，留空则禁用邮件发送 | 无 |
| `SMTP_PORT` | SMTP 端口（587 = STARTTLS，465 = 隐式 TLS） | `587` |
| `SMTP_USER` | SMTP 登录用户名 | 无 |
| `SMTP_PASSWORD` | SMTP 登录密码 | 无 |
| `SMTP_FROM` | 发件人地址（如 `noreply@example.com`） | 无 |

> **注意**：使用 163/QQ 等国内邮箱时，端口 465 需隐式 TLS，端口 587 走 STARTTLS，系统会自动按端口选择。

### 3. Claude CLI 认证

若使用 API key 方式，`.env` 中填写 `ANTHROPIC_API_KEY` 即可自动认证；若使用交互式登录，在容器启动后执行：

```bash
docker compose exec backend claude auth login
```

---

## 快速启动

将仓库 clone 到本地后，在根目录执行：

### 开发模式

源码 bind-mount 进容器，改动立即生效（前端 HMR）：

```bash
make dev    # 构建并启动（首次较慢）
make down   # 停止并移除容器
```

### 生产模式

代码烤入镜像，`next build` 在构建阶段完成：

```bash
make prod       # 构建并启动
make prod-down  # 停止并移除容器
```

### 访问地址

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

> 用户只访问 `:80`（Next.js），`/api/*` 由前端反代到后端，后端不对宿主暴露。

---

## 项目结构

```
backend/app/
  api/        # 路由层：参数校验、鉴权、转发（禁止业务逻辑）
  services/   # 业务逻辑，单一职责
  models/     # SQLAlchemy ORM 模型
  schemas/    # Pydantic 请求/响应 schema
  core/       # 配置、DB 连接、鉴权中间件
  engine/     # 【唯一 LLM 出口】EngineProtocol + ClaudeCliEngine
  storage/    # StorageProtocol + LocalStorage
  tasks/      # 后台任务：归类 worker、任务状态与重试
infra/postgres/
  init.sql        # CREATE EXTENSION
  migrations/     # 001…030，启动时自动顺序执行
docs/             # PRD / DESIGN / ROADMAP / WORKFLOW / SECURITY
```

---

## 文档

| 文档 | 说明 |
|------|------|
| [docs/PRD.md](docs/PRD.md) | 产品需求 |
| [DESIGN.md](DESIGN.md) | 架构设计与 API 契约 |
| [docs/ROADMAP.md](docs/ROADMAP.md) | 实现路径与交付记录 |
| [CLAUDE.md](CLAUDE.md) | 开发约定与硬性禁止 |
| [WORKFLOW.md](WORKFLOW.md) | 开发协议 |
| [docs/SECURITY.md](docs/SECURITY.md) | 安全威胁模型 |

---

## 开发约定

- 所有 LLM 调用只经 `app/engine/`，文件存取只经 `app/storage/`
- 所有文档查询强制带 workspace 权限过滤（防越权/IDOR）
- 密钥不硬编码；`storage_key` 服务端生成，防路径穿越
- 详见 [CLAUDE.md](CLAUDE.md)
