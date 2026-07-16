# 实现路径 · KB-Agent

## 模块总览
| 模块 ID | 模块名 | 核心职责 | 状态 |
|---------|-------|---------|------|
| M0 | 骨架与引擎抽象 | 目录、配置、DB 连接、EngineProtocol+ClaudeCliEngine | ✅ 已交付 |
| M1 | 认证与空间 | 登录/JWT、workspace、成员、鉴权、管理员种子、域名白名单(DB) | ✅ 已交付 |
| M2 | 文档入库与归类 | 上传、本地存储、后台归类(CLI读原文/Bedrock)、任务可观测、分类、目录、删/移/替 | ✅ 已交付 |
| M3 | 对话式检索取件 | Agent 式索引问答、答案+原文链接、多轮上下文、SSE 流式 | ✅ 已交付 |
| MF | 前端（单端口入口） | Next.js+Tailwind、登录/对话(气泡+流式)/文档(目录树)/空间/用户/设置页 | ✅ 已交付 |
| F1–F11 | 增强批次 | 拖拽、批量/目录上传、全字段展示、用户管理、用户组、RBAC（含 stats 模块）、空间按组授权、分类迁移、体验优化、功能扩展、Agent 增强（两阶段全文拉取、Markdown 正文、时间戳注入、提示词版本管理） | ✅ 已交付 |
| F12 | 收尾优化 | NavBar 深色主题、管理入口合并（admin+settings）、聊天引导问题（全局 + 每空间独立）、用户角色合并（internal/partner→user，migration 012） | ✅ 已交付 |
| F13 | 生产部署 | docker-compose.prod.yml（代码烤入镜像，next build 构建阶段完成）、Makefile prod/prod-down、entrypoint.sh 非 root 运行 | ✅ 已交付 |
| F14 | 前端升级 | Next.js 15→16.2.10 + React 18→19 升级；全部页面/组件兼容 | ✅ 已交付 |
| F15 | 文档重命名 | `PATCH /documents/{id}/rename` 端点 + 前端文档列表内联重命名 | ✅ 已交付 |
| F15b | 上传限制 | `proxyClientMaxBodySize: "200mb"`，前端单次上传最大 200 MB | ✅ 已交付 |
| F16 | 按任务模型配置 | 系统设置新增模型配置面板；`model::classify / chat / whatsnew / title` 四个 `app_settings` key；engine 调用时按 key 读取模型 | ✅ 已交付 |
| F17 | 国际化（i18n） | next-intl 客户端 i18n；5 语言（zh/zh-TW/en/ja/ko）；NavBar 切换器；localStorage 持久化；DialogProvider 替换 window.confirm/prompt | ✅ 已交付 |
| F18 | 自助找回密码 | 邮箱 6 位验证码（10 分钟有效）；1 分钟发送限速；5 次错误锁定；uniform 响应防枚举；前端 forgot/reset 流程；migration 019 新增 4 列 | ✅ 已交付 |
| F19 | 任务级 HTTP Header 配置 | 4 类 LLM 任务（归类/标题/对话路由/对话回答）各自可配 HTTP Header，供 Portkey 等网关路由；`task_headers::*` 持久化；OpenAI 兼容引擎透传，ClaudeCliEngine 静默忽略；系统设置 key-value 编辑器 UI | ✅ 已交付 |
| M4 | Skill 插拔框架 | SkillBase 抽象、registry、invoke、审批契约 | 预留（未实现） |
| M5 | SCM 示范 skill | PANW 配置生成，pending_approval→approve→下发 | 预留（未实现） |

> 详细的已交付 Unit 见 git tag（`M1-U*-done` … `F8-done`）。以下模块拆解为历史实现记录；增强批次 F1–F8 的验收见 PRD 第 2 节。

---

## 模块 M0 · 骨架与引擎抽象

**目标**：可运行的 FastAPI 骨架 + DB 连接 + 唯一 LLM 出口抽象。

**产出契约**：分层目录；`app/core/config.py`；`app/engine/base.py` + `ClaudeCliEngine`；健康检查端点。

| Unit ID | 名称 | 内容 | 预估改动 | 验收 |
|---------|------|------|---------|------|
| M0-U1 | 依赖与配置 | pyproject/requirements、settings（读 .env）、.env.example | ~60 行 | `uvicorn` 起服务，GET /health 返 200 |
| M0-U2 | DB 连接与基类 | SQLAlchemy async engine、session 依赖、Base | ~60 行 | 连上 PG，建表脚本可跑 |
| M0-U3 | EngineProtocol | `base.py` 定义 Protocol + EngineResult | ~40 行 | pyright 通过 |
| M0-U4 | ClaudeCliEngine | 子进程调 `claude`，超时/工作目录/错误处理 | ~90 行 | 单测 mock 子进程，返回结构正确 |
| M0-U5 | 引擎工厂 | `ENGINE_BACKEND` 选择实现 | ~30 行 | 配置切换返回对应实现（未实现的抛清晰错误） |

**M0 DoD**：服务能起；/health 绿；engine 抽象有单测；无业务逻辑混入。

---

## 模块 M1 · 认证与空间

**目标**：邮箱+密码登录、JWT、workspace 与成员、鉴权中间件。

**产出契约**：API `/auth/*`、`/workspaces*`；表 users/workspaces/workspace_members；依赖 `require_auth`、`require_admin`、`require_ws_member`。

| Unit ID | 名称 | 内容 | 预估改动 | 验收 |
|---------|------|------|---------|------|
| M1-U1 | 表+迁移 | users/workspaces/workspace_members 建表 | ~50 行 | 迁移跑通，字段齐全 |
| M1-U2 | schema+model | Pydantic + ORM | ~70 行 | pyright 通过 |
| M1-U3 | 密码哈希+JWT 工具 | bcrypt 封装、JWT 签发/校验 + 单测 | ~60 行 | pytest 含边界用例 |
| M1-U3b | 注册+域名白名单 | POST /auth/register，校验 DB `allowed_domains` 表 | ~60 行 | 白名单内返 201；白名单外返 403；重复返 409 |
| M1-U4 | 登录+/auth/me | POST /auth/login、GET /auth/me | ~80 行 | 正确凭据返 JWT；无 token 返 401 |
| M1-U5 | 鉴权依赖 | require_auth / require_admin | ~50 行 | 非 admin 访问管理端点返 403 |
| M1-U6 | 空间 CRUD+成员 | 建空间、加成员、空间列表 | ~120 行 | 非成员看不到空间；Partner 隔离生效 |
| M1-U7 | require_ws_member | 空间成员校验依赖 | ~40 行 | 非成员访问空间资源返 403 |

**M1 DoD**：注册(白名单)→登录→建空间→加成员→列表全链路通；Partner 看不到未授权空间；API 路径与 DESIGN.md 100% 一致。

---

## 模块 M2 · 文档入库与归类

**目标**：上传文件 → 存原文 → 抽取正文 → Agent(经 engine) 归类总结 → 入库可检索。

**产出契约**：API `/workspaces/{ws}/documents`、`/documents/{id}`、`/documents/{id}/download`、`/categories`；表 categories/documents。

| Unit ID | 名称 | 内容 | 预估改动 | 验收 |
|---------|------|------|---------|------|
| M2-U1 | categories 表+CRUD | 分类体系（层级），管理员维护 | ~90 行 | 建分类返 201；非 admin 返 403 |
| M2-U2 | documents+processing_tasks 表 | 含 search_tsv + GIN 索引；任务表 | ~80 行 | 迁移跑通，索引存在 |
| M2-U3 | 本地存储封装 | StorageProtocol + LocalStorage（save/open_path/download_url） | ~90 行 | 存原文后能拿本地路径与限时下载 URL |
| M2-U4 | 上传端点 | POST documents，存原文，建 processing 任务 | ~90 行 | 返 202+status=processing；任务入队 |
| M2-U5 | 归类 worker（后台+日志+重试） | 后台任务调 engine 让 CLI 读原文，一趟产出 分类+摘要+标签+content_text，写库 | ~150 行 | status→ready；category 属预定义；summary/tags/content_text 非空；失败落 error 可重试 |
| M2-U6 | 任务可观测端点 | GET /documents/{id}/tasks、POST /documents/{id}/reprocess | ~80 行 | 返回任务状态+日志；reprocess 重新入队 |
| M2-U7 | 列表/详情/下载 | 过滤、详情、限时下载端点 | ~110 行 | 跨空间不可见；非成员下载 403 |

**M2 DoD**：上传→后台归类(可查进度/失败可重试)→列表看到分类摘要→下载原文全链路通；归类只经 engine(CLI 读原文)；文件存取只经 storage；workspace 过滤生效。

---

## 模块 M3 · 对话式检索取件

**目标**：对话查询 → 全文检索命中文档 → 原文交 engine 生成答案 + 原文链接。

**产出契约**：API `/chat`、`/conversations/{id}`；表 conversations/messages。

| Unit ID | 名称 | 内容 | 预估改动 | 验收 |
|---------|------|------|---------|------|
| M3-U1 | conversations/messages 表 | 建表+迁移 | ~50 行 | 迁移跑通 |
| M3-U2 | 检索 service | PG 全文检索 + workspace/分类过滤，命中排序 | ~100 行 | 命中集合只含所属空间文档 |
| M3-U3 | 答案生成 | 取命中原文交 engine，产出 answer+sources | ~110 行 | answer 非空；sources 每项含 download_url |
| M3-U4 | /chat 端点 | 串起检索+生成+落库 | ~90 行 | 返回 answer+sources+conversation_id |
| M3-U5 | 会话历史 | 多轮上下文（P1） | ~70 行 | 同 conversation_id 带历史 |

**M3 DoD**：提问→检索→带原文链接的答案全链路通；无命中时明确告知“未找到”，不编造；仅限所属空间。

---

## 模块 MF · 前端（单端口入口）

**目标**：Next.js（App Router）+ TS + Tailwind 前端，作为用户唯一入口，反代后端 API。

**产出契约**：frontend/ 项目；rewrites `/api/*`→后端；四个页面；lib/api（统一注入 token）+ lib/auth（token 存取 + 路由守卫）；docker-compose 增加 frontend 服务。

| Unit ID | 名称 | 内容 | 预估改动 | 验收 |
|---------|------|------|---------|------|
| MF-U1 | 脚手架 + 单端口 | Next.js+TS+Tailwind 初始化；next.config rewrites `/api/*`→backend；compose 加 frontend | ~120 行 | 前端起在单端口；/api/health 经反代返 200 |
| MF-U2 | api client + auth | lib/api（fetch 封装，注入 Bearer，401 处理）+ lib/auth（token 存取、路由守卫） | ~120 行 | 未登录跳登录；请求自动带 token |
| MF-U3 | 登录/注册页 | 表单、错误提示、成功后跳转 | ~150 行 | 登录成功进主界面；注册域名外报错 |
| MF-U4 | 对话查询页 | 聊天 UI；答案 + 来源原文链接；无命中提示；LLM 产物净化渲染 | ~200 行 | 提问得答案+可下载来源；Markdown 已 sanitize |
| MF-U5 | 文档管理页 | 上传、列表、归类状态轮询、下载（admin） | ~200 行 | 上传→processing→ready；可下载 |
| MF-U6 | 空间/成员/分类管理页 | 建空间、加成员、维护分类；管理功能按角色显隐 | ~200 行 | admin 可操作；非 admin 隐藏入口 |

**MF DoD**：用户仅访问一个端口即可完成 登录→(管理员)建空间/上传→归类完成→对话查询取原文 全流程；前端无硬编码后端地址；LLM 产物渲染已净化（无 XSS）；非 admin 看不到管理入口。

---

## 模块 M4 · Skill 插拔框架（预留，P1）

**目标**：定义 skill 抽象与注册/调用/审批契约，不实现具体 skill。

| Unit ID | 名称 | 内容 | 验收 |
|---------|------|------|------|
| M4-U1 | SkillBase 抽象 | name/描述/输入schema/是否写操作/invoke | pyright 通过 |
| M4-U2 | registry | 发现+注册 skill | 列出已注册 skill |
| M4-U3 | invoke 端点 | 写操作返回 pending_approval | 写操作不直接执行 |
| M4-U4 | 审批端点 | /actions/{id}/approve 后才执行 | 未审批不执行 |

---

## 模块 M5 · SCM 示范 skill（预留，P1）

**目标**：借助知识生成 PANW 产品配置，人工确认后下发。

| Unit ID | 名称 | 内容 | 验收 |
|---------|------|------|------|
| M5-U1 | SCM skill 骨架 | 继承 SkillBase，标记写操作 | 出现在 /skills |
| M5-U2 | 配置生成 | 经 engine 生成配置方案（只生成） | 产出结构化配置 |
| M5-U3 | 确认后下发 | approve 后调 SCM/PANW API 下发 + 审计日志 | 无 approve 不下发；有审计记录 |

---

## 交付顺序建议

- **Phase 1**：M0 → M1 ✅
- **Phase 2**：M2 ✅
- **Phase 3**：M3（后端 MVP 可用）✅
- **Phase 4**：MF 前端（用户可用的完整 MVP）✅
- **Phase 5**：运维/接入收尾（Bedrock 接入、大 PDF 抽取、测试库隔离）✅
- **Phase 6**：增强批次 F1–F11（拖拽/批量上传/全字段/用户管理/组/RBAC/空间组授权/分类迁移/体验优化/功能扩展/Agent 增强）✅
- **Phase 6b**：收尾与生产部署 F12–F13（NavBar/管理入口/引导问题/角色合并/生产 Docker）✅
- **Phase 6c**：功能完善 F14–F17（Next.js 16 升级、文档重命名、上传 200MB 限制、按任务模型配置、5 语言 i18n）✅
- **Phase 7（未来）**：M4 Skill 框架 → M5 SCM skill

每完成一个 Unit，建议 `git tag M<N>-U<N>-done`，方便回退。
