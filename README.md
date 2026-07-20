# KB-Agent — 让团队知识成为会思考的协作资产

> **AI-Native 多人协同知识管理平台**
> 以 Claude 为核心引擎，把企业文档变成可对话、可生成、可执行的知识网络，让团队用自然语言高效协同。

[![AI Powered](https://img.shields.io/badge/AI-Claude%20Powered-blueviolet)](#)
[![Tech Stack](https://img.shields.io/badge/Stack-Next.js%2016%20%7C%20FastAPI%20%7C%20PostgreSQL%2016-3b82f6)](#)
[![License](https://img.shields.io/badge/License-MIT-10b981)](#)

<h2 align="center"><a href="README.md">中文</a> · <a href="README.en.md">English</a></h2>



## 一句话定位

**KB-Agent = 企业知识库 + 多用户协作空间 + Claude Agent 工作台**

传统知识库是“搜索框 + 文件夹”，信息孤岛、查找低效、协作割裂。KB-Agent 把 Claude 的多步推理、长上下文理解、代码与文档生成能力嵌入到企业知识管理流程中，让团队能够：

- **对话即查询**：用自然语言提问，自动定位原文并生成答案。
- **知识即工作流**：通过 Skill 把 Prompt、业务逻辑和文档处理封装成可复用的 Agent 能力。
- **协同即安全**：多空间隔离、用户组权限、完整审计，满足企业级合规。

---

## 核心能力

### 1. AI 原生知识沉淀
上传 Word、PDF、Excel、PPT、图片等任意格式文档，Claude 自动完成：

- 内容识别（含图片文字提取）
- 智能归类与标签生成
- 摘要与全文索引
- 原文关联，回答可溯源

### 2. 多人协作空间
- **Workspace 隔离**：按业务线、项目、客户或密级建立独立空间。
- **用户组 RBAC**：9 大模块 × 读写级精细授权，内外部人员只能访问被授权内容。
- **新动态订阅**：文档变更自动汇总，通过邮件定期推送给订阅者。

### 3. 聊天 + 工作台（Chat+）
把 Claude 桌面端的能力内嵌到平台中：

- 上传附件、引用知识库原文、多轮对话
- Skill 注入系统提示，让 Agent 完成文档生成、数据整理、报告撰写等复杂任务
- 成果文件在工作台直接下载
- 支持 AI 主动提问（ask-user 协议），实现引导式学习、规划等互动场景

### 4. Skill 共享复用
- 将常用提示词和附属文件封装为 Skill（SKILL.md 格式）
- 平台级 / 空间级共享，按权限可见
- 内置 Claude 官方 Skill，开箱即用
- 降低团队协作门槛，让 Prompt 变成可复用的组织能力

---

## 产品架构

```
用户/管理员
   │
   ├─ 前端 Next.js 16 + React 19 + Tailwind CSS
   ├─ 后端 FastAPI + PostgreSQL（全文检索 + GIN 索引）
   ├─ Agent 引擎：Claude CLI（支持 Anthropic API / Bedrock / 网关）
   ├─ 文件存储：本地/云对象存储（StorageProtocol 抽象）
   └─ 部署：Docker Compose（开发/生产双模式）
```

---

## 为谁设计

| 场景 | 痛点 | KB-Agent 解法 |
|------|------|---------------|
| **企业内部知识沉淀** | 产品手册、技术文档、FAQ 分散，新人查找困难 | 批量上传 → 自动归类 → 对话即查询 |
| **跨团队/外部协作** | 文档权限混乱，敏感信息泄露风险 | 空间隔离 + 用户组 RBAC + 完整审计 |
| **AI 辅助办公** | 员工想调用 AI 生成报告，但缺乏统一入口和权限管控 | 聊天 + 工作台 + Skill 库，成果可下载、可审计 |
| **AI 引导与学习** | 培训、问答需要人工反复介入 | 交互式 Skill 让 AI 主动引导用户 |

---

## 技术栈

| 层 | 技术 |
|----|------|
| Backend | Python 3.12 + FastAPI (async) + Pydantic v2 |
| Frontend | Next.js 16.2.10 + React 19 + TypeScript + Tailwind CSS |
| Database | PostgreSQL 16（全文检索 tsvector + GIN 索引，零向量库依赖） |
| Agent Engine | Claude CLI 子进程封装（EngineProtocol，支持 API Key / Bedrock / 网关） |
| File Storage | 本地文件系统（StorageProtocol 抽象，可替换云对象存储） |
| Deployment | Docker Compose（开发 / 生产双模式） |

---

## 前置条件

### 0. 云主机与 Claude 凭据

- **海外云主机**：Claude CLI 需要访问 Anthropic API，建议部署在海外云主机（如 AWS、GCP、Azure 海外区域）或网络可达 Anthropic 服务的环境。
- **Claude 模型凭据**：任选一种来源：
  - Anthropic 官方 API key（[console.anthropic.com](https://console.anthropic.com)）
  - AWS Bedrock（需开通 Claude 模型权限）
  - Azure 或其他兼容网关（通过 `ANTHROPIC_BASE_URL` 配置）

### 1. 安装 Docker

本项目通过 Docker Compose 运行，需提前安装 [Docker Desktop](https://www.docker.com/products/docker-desktop/)（含 Compose 插件）。

### 2. 配置环境变量

```bash
cp .env.example .env
```

下表列出核心变量含义及默认值：

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
| `ENGINE_IDLE_TIMEOUT_SEC` | 空闲超时秒数 | `300` |

Claude CLI 认证方式三选一：

| 变量 | 说明 |
|------|------|
| `ANTHROPIC_API_KEY` | 方式一：Anthropic 官方 API key |
| `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` | 方式二：自定义网关（如 Portkey） |
| `CLAUDE_CODE_USE_BEDROCK` + AWS 相关密钥 | 方式三：AWS Bedrock |

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

## 企业级安全与合规

- **权限隔离**：Workspace 边界 + 用户组 RBAC，防越权 / IDOR。
- **完整审计**：文件下载、对话记录、Skill 调用均可追溯。
- **密钥管理**：密钥不硬编码，存储 Key 服务端生成，防路径穿越。
- **LLM 统一出口**：所有模型调用只经 `app/engine/`，便于审计与成本控制。
- **部署安全**：Docker Compose 生产模式，支持域名白名单注册。

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

- 所有 LLM 调用只经 `app/engine/`，文件存取只经 `app/storage/`。
- 所有文档查询强制带 workspace 权限过滤（防越权 / IDOR）。
- 密钥不硬编码；`storage_key` 服务端生成，防路径穿越。
- 详见 [CLAUDE.md](CLAUDE.md)。

---

> 让每一次对话，都能激活组织的集体智慧。
