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
| POST | /chat | 对话式检索取件 | {workspace_id, message, [conversation_id]} | {answer, sources:[{doc_id, title, download_url}], conversation_id} |
| GET  | /conversations/{id} | 会话历史 | - | {messages:[...]} |

### Skill（M4 预留，MVP 不实现，仅登记契约）
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
| role | TEXT | NOT NULL, CHECK in ('admin','internal','partner') | 全局角色 |
| created_at | TIMESTAMPTZ | NOT NULL default now() | |

> **注册白名单**：配置项 `ALLOWED_EMAIL_DOMAINS`（如 `company.com,partner-a.com`）。`POST /auth/register` 校验邮箱域名后缀，不在白名单返 403。首个 admin 通过种子脚本/配置创建。

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

## 关键技术选型的“为什么”
- **不上向量库**：用户明确要求以原始文件为准、减少幻觉。检索用 PG 全文 + 元数据过滤定位到「文件」，再把原文交给 Claude 回答，避免向量切片召回不准引入的幻觉。预留在文档量上千后再评估 pgvector。
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
