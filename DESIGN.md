# 架构设计 · KB-Agent

## 系统架构（文字版）

```
                     ┌─────────────────────────────────────────┐
   用户/Partner ──►  │  FastAPI (api/)                          │
   (对话/上传)        │   ├─ auth: JWT + workspace 成员鉴权       │
                     │   ├─ documents: 上传/列表/下载签名URL     │
                     │   ├─ chat: 对话式检索                     │
                     │   └─ (预留) skills: 插拔框架              │
                     └───────┬───────────────────┬──────────────┘
                             │ services/          │
             ┌───────────────┼───────────────┐    │
             ▼               ▼               ▼    ▼
      classify_service  search_service   doc_service   engine/ (唯一LLM出口)
      (调 engine 归类总结) (PG全文检索)   (存取元数据)   ClaudeCliEngine → `claude` 子进程
             │               │               │
             └───────────────┴───────┬───────┘
                                     ▼
                    PostgreSQL (元数据+tsvector) + 对象存储(原始文件)
```

**关键调用链**
- **入库**：上传文件 → `storage`(本地路径) 存原文 → 建 documents(status=processing) + 处理任务 → **后台 worker** 调 `engine` 让 Claude CLI 直接读原文，**一趟产出 {分类归属, 摘要, 标签, content_text 可搜正文}** → 写入 PG（含 `tsvector`）→ status=ready；失败落错误日志、status=failed、支持重试。
- **检索取件**：用户提问 → `search_service` 按 workspace 权限 + 关键词/元数据过滤命中文档 → 取原文/content_text 交给 `engine`(Claude) 生成答案 → 返回「答案 + 每个来源文档的下载链接」。

**为什么归类一趟拿全**：常见文档格式（Word/PDF/图片/Excel/PPT）由 Claude CLI 原生读取，MVP 不自建解析库；让 CLI 在归类同时输出可搜正文 `content_text`，供 PG 全文检索使用，零额外解析依赖。

## 引擎抽象层（为多后端预留）

```python
# app/engine/base.py
class EngineProtocol(Protocol):
    async def complete(self, prompt: str, *, files: list[Path] | None = None,
                       system: str | None = None) -> EngineResult: ...

# MVP 实现：ClaudeCliEngine —— 以子进程方式调用 `claude` CLI（受控、超时、限制工作目录）
# 未来实现：OpenClawEngine / CodexEngine —— 同一 Protocol，配置项 ENGINE_BACKEND 切换
```
约束：所有对 LLM 的调用都经 `EngineProtocol`，业务层不得感知底层是 CLI 还是 SDK。

## 前端架构（单端口入口）

```
       用户浏览器
          │  仅访问一个端口（Next.js，如 :3000 / 生产 :80）
          ▼
   Next.js (frontend/)  ── App Router 页面 + lib/api + lib/auth
          │  next.config.js rewrites: /api/:path*  ->  http://backend:8000/:path*
          ▼
   FastAPI (backend)   ── 不对用户直接暴露端口（仅内网/compose 网络可达）
```

- **单端口**：用户只与 Next.js 交互；所有后端调用走相对路径 `/api/*`，由 rewrites 反代到 FastAPI。规避 CORS，收敛公网暴露面（SECURITY #8）。
- **鉴权**：登录拿 JWT，前端 `lib/auth` 存取；`lib/api` 统一在请求头注入 `Authorization: Bearer`。路由守卫拦截未登录访问。
- **角色显隐**：上传/建空间/建分类/reprocess 等管理功能仅对 admin 显示（仅体验层；后端仍是强制防线）。
- **页面**：①登录/注册 ②对话查询（答案 + 每条来源的原文下载链接）③文档管理（上传、归类状态、列表、下载）④管理后台（空间授权及配置/用户管理）⑤系统设置（通用/提示词/空间管理/用户管理）⑥数据统计 ⑦新动态 ⑧账户设置。
- **引擎选择**：管理员在系统设置切换 Agent 引擎，选择持久化于 `app_settings`（键 `engine_backend`），归类/问答运行时按此解析。Claude CLI 可用；Codex / OpenClaw 前端灰显、后端拒绝（`available=false`），为未来预留。
- **按任务模型配置**：系统设置独立配置归类/对话/新动态/会话标题所用模型，持久化于 `app_settings`（键 `model::classify` / `model::chat` / `model::whatsnew` / `model::title`），engine 调用时按 key 读取；未设则使用引擎默认模型。
- **国际化**：`next-intl` 客户端 i18n；5 语言（`zh` / `zh-TW` / `en` / `ja` / `ko`）；locale 存 `localStorage`，首次访问按 `navigator.language` 匹配；NavBar 右上角语言切换器；`IntlProvider`（动态加载 `messages/*.json`）+ `LocaleContext`；所有 `window.confirm`/`window.prompt` 替换为 `DialogProvider` 提供的 Promise-based 自定义 Modal。
- **技术版本**：Next.js 16.2.10 + React 19。
- **XSS**：LLM 产物（summary/answer）渲染必须净化（SECURITY #6）。

## 存储抽象层（MVP 本地，未来云）

```python
# app/storage/base.py
class StorageProtocol(Protocol):
    async def save(self, key: str, data: bytes) -> str: ...          # 返回 storage_key
    async def open_path(self, key: str) -> Path: ...                 # 供 CLI 读原文的本地路径
    async def download_url(self, key: str, expires_in: int) -> str: ...  # 本地实现返回受控下载端点 URL

# MVP 实现：LocalStorage —— 存到配置的本地目录（LOCAL_STORAGE_DIR），download_url 走后端受限下载端点
# 未来实现：S3Storage / OssStorage —— 同一 Protocol，签名 URL
```
约束：业务层只依赖 `StorageProtocol`，不得直接拼路径读写文件。

## API 契约（一旦确定，后续步骤不得私自修改路径与语义）

### 认证与空间（M1）
| 方法 | 路径 | 说明 | 请求体关键字段 | 返回关键字段 |
|------|------|------|--------------|-------------|
| POST | /auth/register | 注册（**邮箱域名后缀须在白名单内**） | {email, password} | 201 {id, email} / 403 域名不允许 / 409 已存在 |
| POST | /auth/login | 登录 | {email, password} | {access_token, role} |
| GET  | /auth/me | 当前用户 | - | {id, email, role} |
| POST | /auth/change-password | 改自己的密码 | {current_password, new_password} | 204 / 400 当前密码错 / 401 |
| GET  | /workspaces | 我可见的空间列表 | - | [{id, name, role_in_ws}] |
| POST | /workspaces | 建空间（管理员） | {name, description} | {id, ...} |
| POST | /workspaces/{id}/members | 加成员（管理员） | {user_id, role} | {ok} |

### 文档（M2）
| 方法 | 路径 | 说明 | 请求体关键字段 | 返回关键字段 |
|------|------|------|--------------|-------------|
| POST | /workspaces/{ws}/documents | 上传文档（管理员，触发归类总结） | multipart: file, [category_hint] | {id, status:"processing"} |
| GET  | /workspaces/{ws}/documents | 列表（按分类/标签过滤） | ?category&tag&page&size | [{id, title, category, tags, summary}] |
| GET  | /documents/{id} | 单文档元数据 | - | {id, title, category, tags, summary, status} |
| GET  | /documents/{id}/download | 获取原文下载 URL（本地受控下载端点，限时） | - | {url, expires_in} |
| GET  | /documents/{id}/tasks | 该文档的处理任务与日志（查进度/排错） | - | [{task_id, status, attempts, error, logs}] |
| POST | /documents/{id}/reprocess | 归类失败后手动重试（管理员） | - | {task_id, status:"queued"} |
| GET  | /categories | 分类体系（管理员维护） | ?workspace | [{id, name, parent_id}] |
| POST | /categories | 新建分类（管理员） | {workspace_id, name, parent_id?} | {id, ...} |

### 对话检索（M3）
| 方法 | 路径 | 说明 | 请求体关键字段 | 返回关键字段 |
|------|------|------|--------------|-------------|
| POST | /chat | 对话式检索取件（非流式） | {workspace_id, message, [conversation_id]} | {answer, sources:[{doc_id, title, download_url}], conversation_id} |
| POST | /chat/stream | SSE 流式：先推工作阶段，再推答案 | 同上 | event: stage / done |
| GET  | /conversations | 我的会话列表 | ?workspace_id | [{id, workspace_id, created_at}] |
| POST | /conversations | 新建空会话 | {workspace_id} | {id, ...} |
| GET  | /conversations/{id} | 会话历史 | - | {messages:[...]} |

### 目录 / 文档管理（M2 增强 · F1/F2/F8）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /folders | 列/建目录（层级，parent_id） |
| PATCH | /folders/{id} | 重命名 |
| PATCH | /folders/{id}/move | 改父级（防环） |
| DELETE | /folders/{id} | 删目录（子级级联，文档移出不删） |
| PATCH | /documents/{id}/move | 移动文档到目录 |
| PATCH | /documents/{id}/rename | 重命名文档标题（管理员） |
| DELETE | /documents/{id} | 删除文档（存储+DB+任务+索引） |
| POST | /documents/{id}/replace | 替换原文并重新归类 |

### 用户管理 / 组 / RBAC（F4/F5/F6，均 admin-only）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /admin/users | 列出所有用户 |
| PATCH | /admin/users/{id}/active | 启用/禁用 |
| PATCH | /admin/users/{id}/role | 改角色 |
| POST | /admin/users/{id}/reset-password | 重置密码 |
| GET/POST | /admin/groups | 列/建用户组 |
| DELETE | /admin/groups/{id} | 删组 |
| GET/POST | /admin/groups/{id}/rules | 列/加入组规则 |
| DELETE | /admin/rules/{id} | 删规则 |
| GET | /admin/groups/{id}/members | 组成员 |
| POST | /admin/recompute-memberships | 全量重算自动入组 |
| GET/PUT | /admin/groups/{id}/permissions | 查/设组的模块权限 |
| GET | /auth/my-permissions | 当前用户各模块有效权限（菜单显隐用） |

### 空间按组授权（F7）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /workspaces/{ws}/group-grants | 列出空间的组授权 |
| POST | /workspaces/{ws}/group-grants | 授权空间给组 {group_id, role_in_ws} |
| DELETE | /workspaces/{ws}/group-grants/{group_id} | 撤销 |

### 系统设置（管理员）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PUT | /settings/engine | 查/设引擎后端（Claude 可用；Codex/OpenClaw 灰显） |
| GET/PUT | /settings/models | 查/设各任务模型（`classify` / `chat` / `whatsnew` / `title`，每个 task 独立，持久化 `model::*` key） |
| GET/POST | /auth/allowed-domains | 注册域名白名单（DB 维护） |
| DELETE | /auth/allowed-domains/{id} | 删白名单域名 |
| GET/PUT | /settings/brand | 品牌配置（Logo/名称） |
| GET/PUT | /settings/smtp | SMTP 邮件配置 |
| GET/PUT | /settings/whatsnew-schedule | 新动态定时配置（频率/小时） |
| GET/PUT | /settings/prompts/{key} | 提示词查/设（含版本历史） |
| GET | /settings/prompts/{key}/history | 提示词版本历史 |
| POST | /settings/prompts/{key}/rollback/{version_id} | 回滚到指定版本 |
| GET | /settings/workspaces/{ws}/suggested-questions | 查空间引导词（登录用户，fallback 全局） |
| PUT | /settings/workspaces/{ws}/suggested-questions | 设空间引导词（管理员） |

### 数据统计（F9/admin）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /stats/usage | 用量报表（按天/用户/动作聚合） |
| GET | /stats/downloads | 下载记录清单 |
| GET | /stats/conversations | 对话记录清单 |
| GET | /stats/logs | 系统日志查看 |

### 新动态（F10/F11）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /whatsnew | 当前用户可见的新动态报告列表 |
| POST | /whatsnew/trigger | 手动触发所有空间新动态生成（管理员） |
| GET | /whatsnew/subscription | 查当前用户订阅 |
| PUT | /whatsnew/subscription | 设订阅频率（weekly/biweekly/monthly）|
| DELETE | /whatsnew/subscription | 取消订阅 |

### 空间管理增强（F10）
| 方法 | 路径 | 说明 |
|------|------|------|
| DELETE | /workspaces/{id} | 删除空间（管理员） |
| GET | /workspaces/{id}/download-all | 打包下载空间全部文档（管理员） |

### 会话管理增强（F10/F11）
| 方法 | 路径 | 说明 |
|------|------|------|
| PATCH | /conversations/{id} | 改会话标题 / Pin |
| DELETE | /conversations/{id} | 删除会话 |

### 账户设置
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /auth/change-password | 改自己的密码 |

### Skill（M4 预留，未实现，仅登记契约）
| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | /skills | 列出已注册 skill |
| POST | /skills/{name}/invoke | 调用 skill；写操作返回 {action_id, status:"pending_approval"} |
| POST | /actions/{id}/approve | 人工确认后执行（SCM 下发配置等） |

## 数据模型（一旦确定，后续只做 additive 修改）

### users
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | |
| email | TEXT | UNIQUE, NOT NULL | 登录名；注册时域名后缀须在白名单内 |
| password_hash | TEXT | NOT NULL | bcrypt |
| role | TEXT | NOT NULL, CHECK in ('admin','user') | 全局角色 |
| created_at | TIMESTAMPTZ | NOT NULL default now() | |

> **注册白名单**：存储在 DB `allowed_domains` 表（管理员在系统设置维护）。`POST /auth/register` 校验邮箱域名后缀，不在白名单返 403；白名单为空则全拒绝。
>
> **首个管理员**：配置 `ADMIN_EMAIL` / `ADMIN_PASSWORD`，应用启动时（lifespan）**幂等种子**创建 role=admin 用户，密码 bcrypt 存库。已存在则跳过（尊重用户后续改过的密码）。用户经 `POST /auth/change-password` 自行改密。

### workspaces（隔离边界）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | |
| name | TEXT | NOT NULL | |
| description | TEXT | | |
| created_at | TIMESTAMPTZ | NOT NULL default now() | |

### workspace_members（用户↔空间，决定可见性）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| workspace_id | UUID | FK workspaces, PK | |
| user_id | UUID | FK users, PK | |
| role_in_ws | TEXT | NOT NULL CHECK in ('owner','editor','viewer') | 空间内角色 |

### categories（管理员预定义分类体系，支持层级）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | |
| workspace_id | UUID | FK workspaces, NOT NULL | 分类隶属空间 |
| name | TEXT | NOT NULL | |
| parent_id | UUID | FK categories NULL | 层级；顶层为 NULL |

### documents
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | |
| workspace_id | UUID | FK workspaces, NOT NULL | 隔离键；所有查询必带 |
| title | TEXT | NOT NULL | 原始文件名/抽取标题 |
| storage_key | TEXT | NOT NULL | 对象存储 key（原始文件） |
| mime_type | TEXT | NOT NULL | |
| category_id | UUID | FK categories NULL | Agent 归入的分类 |
| summary | TEXT | | Agent 生成的摘要 |
| tags | TEXT[] | default '{}' | Agent 生成的自由标签 |
| content_text | TEXT | | 抽取的纯文本（供全文检索与喂给 LLM） |
| search_tsv | TSVECTOR | | 由 title+summary+content_text 生成，GIN 索引 |
| status | TEXT | NOT NULL default 'processing' | processing / ready / failed |
| uploaded_by | UUID | FK users | |
| created_at | TIMESTAMPTZ | NOT NULL default now() | |

索引：`GIN(search_tsv)`；`(workspace_id, category_id)`；`(workspace_id, status)`。

### processing_tasks（后台归类任务，可查进度/可重试）
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID | PK | 任务 ID |
| document_id | UUID | FK documents, NOT NULL | 关联文档 |
| kind | TEXT | NOT NULL default 'classify' | 任务类型 |
| status | TEXT | NOT NULL default 'queued' | queued/running/succeeded/failed |
| attempts | INT | NOT NULL default 0 | 已尝试次数（重试用） |
| max_attempts | INT | NOT NULL default 3 | 上限 |
| error | TEXT | | 最近一次失败原因 |
| logs | JSONB | default '[]' | 结构化日志（阶段/耗时/CLI 输出摘要） |
| created_at | TIMESTAMPTZ | NOT NULL default now() | |
| updated_at | TIMESTAMPTZ | NOT NULL default now() | |

索引：`(document_id)`；`(status)`。失败可通过 `POST /documents/{id}/reprocess` 重新入队。

### conversations / messages（M3）
| conversations | 类型 | 约束 |
|------|------|------|
| id | UUID | PK |
| workspace_id | UUID | FK, NOT NULL |
| user_id | UUID | FK, NOT NULL |
| created_at | TIMESTAMPTZ | default now() |

| messages | 类型 | 约束 |
|------|------|------|
| id | UUID | PK |
| conversation_id | UUID | FK conversations |
| role | TEXT | CHECK in ('user','assistant') |
| content | TEXT | NOT NULL |
| sources | JSONB | 引用的 doc_id 列表 |
| created_at | TIMESTAMPTZ | default now() |

### 增强批次新增表（migration 005–016）
- **folders**（F1/F2）：`id, workspace_id(FK), name, parent_id(FK self, ON DELETE CASCADE), created_at`；`documents.folder_id`（FK, ON DELETE SET NULL）。用户手动目录树，与分类/标签解耦。
- **allowed_domains**（M1-U9）：`id, domain(UNIQUE), created_at`。注册白名单迁到 DB。
- **app_settings**（MF-U7）：`key(PK), value, updated_at`。如 `engine_backend`。
- **groups**（F5）：`id, name(UNIQUE), description, created_at`。
- **group_rules**（F5）：`id, group_id(FK), field(email_domain/email/role), op(equals/endswith/contains), value`。
- **group_members**（F5）：`(group_id, user_id)` PK。
- **group_permissions**（F6）：`(group_id, module)` PK, `level CHECK(none/read/write)`；module ∈ chat/documents/workspaces/users/settings/stats/whatsnew。
- **workspace_group_grants**（F7）：`(workspace_id, group_id)` PK, `role_in_ws CHECK(owner/editor/viewer)`。
- **users**（F4）新增 `is_active BOOLEAN default true`。
- **usage_events**（migration 009）：用量统计事件表（用户/动作/时间）。
- **document_brief**（migration 010）：文档 `brief` 字段（两阶段索引摘要）。
- **conversations**（migration 011）新增 `title, is_pinned` 字段（会话命名 + Pin）。
- **users**（migration 012）：合并角色 internal/partner → user；CHECK `('admin','user')`。
- **prompt_history**（migration 013）：提示词版本历史表（key/content/created_at）。
- **whatsnew_reports**（migration 014）：新动态报告表（workspace 级，定时生成）。
- **whatsnew_subscriptions**（migration 015）：用户订阅频率表（weekly/biweekly/monthly）。
- **constraints**（migration 016）：补全约束与索引。

## 关键技术选型的“为什么”
- **不上向量库 / Agent 式索引问答**：以原文为准、减少幻觉。对话不做关键词硬匹配，而是把**整个空间的结构化索引**（标题/分类/标签/摘要）喂给 Claude，由它理解意图、组织答案、按编号挑相关文档（服务端映射回真实文档，防 ID 幻觉）。文档量上千后再评估 pgvector。
- **RBAC 绑用户组 + admin 绕过**：权限挂在组上（组→模块→读写），用户取所属组并集最高；空间访问 = 个人成员 ∪ 组授权。admin 绕过一切，避免把管理员锁在外面。
- **引擎认证经 .env 透传**：支持 API key / 公司网关 / AWS Bedrock，凭据不硬编码；引擎后端由管理员在系统设置持久化选择。
- **封装 Claude CLI 而非直连 SDK**：复用 CLI 的 agent 能力与工具生态；用 `EngineProtocol` 隔离，未来平滑接入 OpenClaw/Codex。
- **workspace 作为隔离边界**：Partner 与内部数据天然分空间，权限模型简单可审计，避免行级复杂 ACL。
- **本地存储 + 存储抽象**：用户要求先不上云对象存储、保持简单。用 `StorageProtocol` 隔离，本地实现 `LocalStorage`，未来换 S3/OSS 不动业务层。
- **归类交给 Claude CLI 读原文**：常见格式 CLI 原生支持，MVP 免自建解析管线；一趟产出可搜正文 `content_text` 供全文检索。
- **后台任务 + 处理任务表**：大文件归类不阻塞上传；`processing_tasks` 记录进度/日志/错误，失败可重试。
- **写操作审批（M4/M5）**：SCM 等会改动真实设备的操作必须 `pending_approval → approve → execute`，杜绝全自动下发。

## 关键约束
- **安全**：云上部署，公网暴露；JWT 鉴权；所有文档访问强制 workspace 成员校验；密钥走云 secret 管理。
- **隔离**：跨 workspace 数据零泄漏，查询层强制注入 workspace 过滤。

### 越权校验（IDOR 防护）
- 资源端点校验对象归属，不只校验登录态：`/documents/{id}`、`/documents/{id}/download`、`/documents/{id}/tasks`、`/documents/{id}/reprocess` 均须 `require_ws_member(doc.workspace_id)`。
- workspace 过滤下沉到 SQL：列表/检索一律 `WHERE workspace_id IN (:my_workspaces)`，禁止查全量再应用层过滤。
- 非成员访问返回 403/404，不泄漏资源是否存在。
- 每个端点配越权测试：成员可访问 + 非成员被拒（含 Partner 跨空间用例）。

### 路径穿越 / 文件存取安全（本地存储）
- `storage_key` 由服务端生成（如 `{workspace_id}/{uuid}`），与客户端文件名解耦；原始文件名仅存 `documents.title`。
- `LocalStorage.open_path` / `download` 内部：拼路径后 `realpath` 规范化，断言结果在 `LOCAL_STORAGE_DIR` 前缀内，否则抛错拒绝。
- 下载端点先按 `document_id` 取记录、校验 workspace 成员，再用记录里的 `storage_key` 取文件；绝不把 query/path 参数直接拼进文件系统路径。
- 下载响应头：`Content-Disposition: attachment; filename="..."` + `X-Content-Type-Options: nosniff`，防止 HTML/SVG 内联渲染导致存储型 XSS。
- **合规/风险**：PANW 配置类操作 MVP 后仅“确认后执行”，保留审计日志与回滚。
- **性能**：MVP 面向千级文档量，全文检索 + GIN 索引足够；单次归类/问答 LLM 调用设超时与并发上限。
