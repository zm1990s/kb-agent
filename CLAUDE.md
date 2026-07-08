# 项目记忆 · KB-Agent

## 身份
你是 **KB-Agent**（内部 + Partner 共享 Agent 知识平台）的架构助手。任何改动前先给计划，等用户确认再执行。

## 项目一句话
面向内部员工与外部 Partner 的共享 Agent 知识平台：管理员上传文档 → Agent 自动归类/总结沉淀为可检索知识 → 用户通过对话查询知识并获取原文；架构预留 Skill 插拔框架（未来接入 SCM 等 skill，可在人工确认后下发 PANW 产品配置）。

## 技术栈（禁止中途更换，如需变更走 /design 流程）
- Backend: **Python 3.11 + FastAPI**（async），Pydantic v2
- 数据库: **PostgreSQL 16**（元数据 + 全文检索 `tsvector`）；**MVP 不引入向量库**（检索走结构化元数据 + 关键词，把原文交给 LLM 回答以降低幻觉）
- 文件存储: **MVP 用本地文件系统**（保持架构简单）；通过 `StorageProtocol` 抽象封装，未来可换云对象存储而不动业务层
- 正文/归类: **交给 Claude CLI 直接读原文**（Word/PDF/图片/Excel/PPT 等常见格式 CLI 原生支持），归类时一趟调用同时产出 {分类, 摘要, 标签, 可搜正文 content_text}，MVP 不自己写解析库
- Agent 引擎: **封装 Claude CLI 子进程**，通过 `EngineProtocol` 抽象层调用；预留 OpenClaw / Codex 等未来后端
- 认证: **自建用户表 + 邮箱密码**，注册时按 **域名后缀白名单** 控制准入
- 异步处理: 归类走 **后台任务**（含处理任务表 + 详细日志 + 失败可重试）
- 前端: **Next.js（App Router）+ TypeScript + Tailwind**。**只对用户暴露一个端口**——Next.js 作统一入口，经 rewrites 把 `/api/*` 反代到后端 FastAPI，用户不直接访问后端端口
- 部署: **云上部署**（本地开发用 Docker Compose；对象存储 MVP 暂用本地路径）

## 目录约定
```
backend/
  app/
    api/          # 路由层：只做参数校验、鉴权、转发，禁止业务逻辑
    services/     # 业务逻辑，单一职责（doc_service / search_service / classify_service ...）
    models/       # SQLAlchemy ORM 模型
    schemas/      # Pydantic 请求/响应 schema
    core/         # 配置、DB 连接、鉴权中间件、异常处理
    engine/       # 【唯一 LLM 出口】EngineProtocol + ClaudeCliEngine，未来加 OpenClawEngine/CodexEngine
    skills/       # 【预留】skill 插拔框架：SkillBase 抽象 + registry
    storage/      # StorageProtocol + LocalStorage（MVP 本地路径），未来加 S3/OSS 实现
    tasks/        # 后台任务：归类 worker、任务状态与重试
  tests/
frontend/         # Next.js（App Router）+ TS + Tailwind，用户唯一入口
  app/            # 路由页面：login/chat/documents/admin/users/settings
  lib/            # api client（统一走 /api，含 stream SSE）、auth、useAuthGuard
  components/     # NavBar(RBAC 显隐) / MessageBubble / Markdown / FolderTree
                  # / TaskLogPanel / admin(WorkspaceAdmin/SystemSettings/CategoryManager)
  next.config.js  # rewrites: /api/* -> 后端 FastAPI（单端口暴露）
infra/
  postgres/
    init.sql          # CREATE EXTENSION
    migrations/       # 001_m1_auth … 008_rbac，按序应用
scripts/          # dev.sh / test.sh(独立库 kbagent_test) / lint.sh / e2e.sh
docs/                 # PRD / DESIGN / ROADMAP / WORKFLOW / SECURITY
prompts/              # 分步系统提示词
```

## 硬性禁止
- 禁止修改 `.env`（只改 `.env.example`）
- 禁止直连外部 LLM SDK/API —— 所有 LLM 调用只走 `app/engine/`（当前实现为 Claude CLI 子进程）
- 禁止在 `api/` 层写业务逻辑（业务归 `services/`）
- 禁止把 API key / 云凭据 / CLI 密钥硬编码进任何代码文件（云端走 secret 管理，本地走 `.env`）
- 禁止在业务层直接拼本地文件路径读写 —— 文件存取只走 `app/storage/`（StorageProtocol）
- 禁止跳过域名白名单校验创建用户 —— 注册必须过白名单
- 禁止让归类失败静默 —— 处理任务必须落错误日志且可重试

### 前端（frontend/）
- 禁止在前端硬编码后端地址 —— 一律走相对路径 `/api/*`，由 Next.js rewrites 反代（单端口）
- 禁止用 `dangerouslySetInnerHTML` 渲染未净化内容 —— LLM 产物（summary/answer）含攻击者可控文本，Markdown 渲染必须 sanitize（如 DOMPurify）（SECURITY #6 存储型 XSS）
- 禁止把 JWT 明文散落多处 —— 统一经 `lib/auth` 存取；请求统一经 `lib/api` 注入 Authorization
- 禁止在前端做权限判定作为唯一防线 —— 后端已强制鉴权，前端仅做显隐/体验
- 禁止修改已建好的数据库表结构（只做 additive 增量迁移）
- 禁止跨 workspace 读取文档 —— 所有文档查询必须带 workspace 权限过滤

### 越权校验（每个资源端点强制）
- 每个针对具体资源的端点（`/documents/{id}`、`/download`、`/tasks`、`/reprocess` 等）必须校验「当前用户是该资源所属 workspace 的成员」，禁止只校验「已登录」
- workspace 过滤必须下沉到 **SQL 查询层**（`WHERE workspace_id IN (:my_ws)`），禁止「先查全量再在应用层过滤」
- 资源 ID 用 UUID；即使 ID 被猜到/遍历，非成员也必须拿不到数据（返 403/404，不泄漏存在性）
- 管理员端点（建空间/建分类/上传/reprocess/用户管理/组/RBAC）必须过 `require_admin`；空间内资源必须过 `require_ws_member`；每个端点都要有越权测试用例（成员可访问 + 非成员被拒）

### 权限模型（RBAC，F4–F7）
- **admin 绕过一切 RBAC**（`effective_permissions` 对 admin 返回全模块 write）——改动权限逻辑时保持这条不变，避免锁死管理员。
- 权限绑**用户组**（组→模块→none/read/write）；用户取所属组权限并集最高。模块 = chat/documents/workspaces/users/settings。
- 空间访问 = 个人成员 ∪ 所属组授权（`is_member`/`list_my_workspaces` 两者都要查）。
- 自动入组规则：注册时 `sync_user_groups`；改规则后靠 `recompute-memberships` 全量重算。
- 引擎工具：**已按决策放开 Claude 全部工具**（含 Bash，供 pdftotext 等）；容器以非 root 运行；提示词注入由外部 Guardrails 兜底。不要再收窄成 allowedTools 而破坏大文件抽取。

### 路径穿越 / 文件存取（storage 层强制）
- 禁止用客户端提供的文件名当存储路径 —— `storage_key` 由服务端生成（UUID），原始文件名只存 DB 字段
- 存取文件时必须规范化路径（`os.path.realpath`）并校验结果仍在 `LOCAL_STORAGE_DIR` 之内，落在根目录外一律拒绝
- 下载端点必须先校验 `storage_key` 属于该文档记录，再由 storage 层取路径；禁止把请求参数直接拼进文件路径
- 下载响应强制 `Content-Disposition: attachment` + `X-Content-Type-Options: nosniff`，禁止让浏览器内联渲染上传内容（防存储型 XSS）
- 禁止让 skill 类操作（如 SCM 下发配置）绕过「人工确认后执行」审批 —— 未来 M5 强制约束
- 禁止把多个功能塞进一个巨大文件

## 强制流程
- 改动前：先给计划，等用户确认再改文件
- 改动后：自己跑 lint（ruff）+ 类型检查（pyright/mypy）+ 测试（pytest）验收
- 新增依赖：先询问是否必须，列出替代方案
- 遇到不确定的地方：**明确说“我不确定”**，不要硬猜
- 每完成一个 Unit：跑其验收命令，绿了再进下一个，并向用户汇报
