# KB-Agent — Turn Team Knowledge into Collaborative Thinking Assets

> **AI-Native Multi-User Collaborative Knowledge Management Platform**
> Powered by Claude, it transforms enterprise documents into a conversational, generative, and executable knowledge network, enabling teams to collaborate efficiently in natural language.

[![AI Powered](https://img.shields.io/badge/AI-Claude%20Powered-blueviolet)](#)
[![Tech Stack](https://img.shields.io/badge/Stack-Next.js%2016%20%7C%20FastAPI%20%7C%20PostgreSQL%2016-3b82f6)](#)
[![License](https://img.shields.io/badge/License-MIT-10b981)](#)

<h2 align="center"><a href="README.md">中文</a> · <a href="README.en.md">English</a></h2>



## One-Line Positioning

**KB-Agent = Enterprise Knowledge Base + Multi-User Collaboration Space + Claude Agent Workbench**

Traditional knowledge bases are "search box + folders", leading to information silos, inefficient search, and fragmented collaboration. KB-Agent embeds Claude's multi-step reasoning, long-context understanding, and document/code generation capabilities into enterprise knowledge workflows, enabling teams to:

- **Conversation as Query**: Ask questions in natural language; answers are generated with cited source documents.
- **Knowledge as Workflow**: Package prompts, business logic, and document processing into reusable Agent capabilities via Skills.
- **Collaboration as Security**: Multi-space isolation, user-group RBAC, and full audit trails meet enterprise compliance requirements.

---

## Core Capabilities

### 1. AI-Native Knowledge Ingestion
Upload documents in any format — Word, PDF, Excel, PPT, images, and more. Claude automatically:

- Recognizes content (including text extraction from images)
- Categorizes and tags intelligently
- Generates summaries and full-text indexes
- Links answers back to original sources

### 2. Multi-User Collaboration Spaces
- **Workspace Isolation**: Create independent spaces by business line, project, client, or classification level.
- **User-Group RBAC**: Fine-grained read/write permissions across 9 modules, so internal and external members only access authorized content.
- **Activity Subscriptions**: Document changes are summarized and emailed to subscribers on a regular schedule.

### 3. Chat + Workbench (Chat+)
Embed the power of Claude Desktop into the platform:

- Upload attachments, cite knowledge-base sources, and have multi-turn conversations
- Inject system prompts via Skills so the Agent can handle complex tasks like document generation, data organization, and report writing
- Download produced files directly from the workbench
- Support AI-initiated questions (ask-user protocol) for guided learning, planning, and interactive scenarios

### 4. Skill Sharing & Reuse
- Encapsulate frequently used prompts and supporting files as Skills (SKILL.md format)
- Share at platform level or workspace level, visible according to permissions
- Includes official Claude Skills, ready to use out of the box
- Lower the barrier to team collaboration by turning prompts into reusable organizational capabilities

---

## Product Architecture

```
Users / Admins
   │
   ├─ Frontend: Next.js 16 + React 19 + Tailwind CSS
   ├─ Backend: FastAPI + PostgreSQL (full-text search + GIN indexes)
   ├─ Agent Engine: Claude CLI / Codex CLI (EngineProtocol abstraction, supports multiple backends)
   ├─ File Storage: local / cloud object storage (StorageProtocol abstraction)
   └─ Deployment: Docker Compose (dev / production dual modes)
```

---

## Who It's For

| Scenario | Pain Point | KB-Agent Solution |
|----------|------------|-------------------|
| **Enterprise Knowledge Consolidation** | Product manuals, technical docs, and FAQs are scattered; new hires struggle to find information | Bulk upload → auto categorization → conversational query |
| **Cross-Team / External Collaboration** | Document permissions are chaotic, risking sensitive data leaks | Space isolation + user-group RBAC + full audit |
| **AI-Assisted Office Work** | Employees want AI-generated reports but lack a unified entry point and permission controls | Chat + Workbench + Skill library, with auditable, downloadable output |
| **AI-Guided Learning** | Training and Q&A require repeated manual intervention | Interactive Skills let AI proactively guide users |

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Backend | Python 3.12 + FastAPI (async) + Pydantic v2 |
| Frontend | Next.js 16.2.10 + React 19 + TypeScript + Tailwind CSS |
| Database | PostgreSQL 16 (full-text search tsvector + GIN indexes, zero vector DB dependency) |
| Agent Engine | Claude CLI / Codex CLI subprocess wrapper (EngineProtocol abstraction, supports multiple backends) |
| File Storage | Local filesystem (StorageProtocol abstraction, swappable to cloud object storage) |
| Deployment | Docker Compose (dev / production dual modes) |

---

## Prerequisites

### 0. Cloud Host & Claude Credentials

- **Overseas cloud host**: Claude CLI needs to reach the Anthropic API. We recommend deploying on an overseas cloud host (e.g., AWS, GCP, Azure overseas regions) or any environment with network access to Anthropic services.
- **Claude model credentials**: Choose one of the following:
  - Anthropic official API key ([console.anthropic.com](https://console.anthropic.com))
  - AWS Bedrock (requires Claude model permissions)
  - Azure or another compatible gateway (configure via `ANTHROPIC_BASE_URL`)

### 1. Install Docker

This project runs on Docker Compose. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes the Compose plugin) in advance.

### 2. Configure Environment Variables

```bash
cp .env.example .env
```

The table below lists the meaning and default values of the core variables:

#### Database

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg driver) | `postgresql+asyncpg://kbagent:kbagent@postgres:5432/kbagent` |

#### Authentication

| Variable | Description | Default |
|----------|-------------|---------|
| `JWT_SECRET` | JWT signing key. **Must be changed to a random long string in production** | None (required) |
| `JWT_EXPIRE_MIN` | Token validity period (minutes) | `60` |
| `ADMIN_EMAIL` | First administrator email; leave blank to skip creation | None |
| `ADMIN_PASSWORD` | First administrator password. **Use a strong password in production** | None |

#### Agent Engine

| Variable | Description | Default |
|----------|-------------|---------|
| `ENGINE_BACKEND` | Engine type: `claude_cli` (default) / `codex` | `claude_cli` |
| `CLAUDE_CLI_PATH` | Claude CLI executable path | `claude` |
| `CLAUDE_MODEL` | Specify model (leave blank to use CLI default) | None |
| `ENGINE_IDLE_TIMEOUT_SEC` | Idle timeout in seconds | `300` |

Claude CLI authentication options (choose one):

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Option 1: Anthropic official API key |
| `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN` | Option 2: Custom gateway (e.g., Portkey) |
| `CLAUDE_CODE_USE_BEDROCK` + AWS credentials | Option 3: AWS Bedrock |

Codex CLI (applies when `ENGINE_BACKEND=codex`):

| Variable | Description | Default |
|----------|-------------|---------|
| `CODEX_CLI_PATH` | Codex CLI executable path | `codex` |
| `CODEX_CONFIG_DIR` | Config directory (contains `config.toml` / `hooks.json`) | `/app/codex_config` |
| `OPENAI_API_KEY` | Azure OpenAI API key | None |

#### File Storage

| Variable | Description | Default |
|----------|-------------|---------|
| `STORAGE_BACKEND` | Storage backend; currently supports `local` | `local` |
| `LOCAL_STORAGE_DIR` | Local storage directory (container path) | None (required) |
| `DOWNLOAD_URL_TTL_SEC` | Download link validity period (seconds) | `3600` |

#### Email Notifications (SMTP)

SMTP supports two configuration methods:

- **System Settings UI** (recommended): After deployment, fill in "System Settings → SMTP Email". No restart required; DB settings take precedence over env.
- **Environment Variables**: Used as initial defaults, suitable for pre-filling on first deployment.

| Variable | Description | Default |
|----------|-------------|---------|
| `SMTP_HOST` | SMTP server address; leave blank to disable email sending | None |
| `SMTP_PORT` | SMTP port (587 = STARTTLS, 465 = implicit TLS) | `587` |
| `SMTP_USER` | SMTP login username | None |
| `SMTP_PASSWORD` | SMTP login password | None |
| `SMTP_FROM` | Sender address (e.g., `noreply@example.com`) | None |

> **Note**: For Chinese email providers such as 163/QQ, port 465 requires implicit TLS, and port 587 uses STARTTLS. The system automatically selects the correct mode based on the port.

### 3. Claude CLI Authentication

If using the API key method, simply set `ANTHROPIC_API_KEY` in `.env` for automatic authentication. For interactive login, run after the container starts:

```bash
docker compose exec backend claude auth login
```

---

## Quick Start

After cloning the repository, run the following commands from the project root:

### Development Mode

Source code is bind-mounted into the container; changes take effect immediately (frontend HMR):

```bash
make dev    # Build and start (first run is slower)
make down   # Stop and remove containers
```

### Production Mode

Code is baked into the image; `next build` runs during the build phase:

```bash
make prod       # Build and start
make prod-down  # Stop and remove containers
```

### Access URLs

```bash
open http://localhost/          # Frontend entry
open http://localhost/api/docs  # Swagger UI
docker compose logs -f frontend backend   # View logs (dev mode)
```

### Other Commands

```bash
make test   # Run pytest inside the backend container
make lint   # Run ruff + pyright inside the backend container
```

> Users only access `:80` (Next.js). `/api/*` is reverse-proxied by the frontend to the backend; the backend is not exposed to the host.

---

## Enterprise Security & Compliance

- **Permission Isolation**: Workspace boundaries + user-group RBAC prevent unauthorized access and IDOR.
- **Full Audit Trail**: File downloads, conversation records, and Skill invocations are all traceable.
- **Secret Management**: Secrets are not hard-coded; storage keys are server-generated to prevent path traversal.
- **Unified LLM Exit**: All model calls go through `app/engine/` only, enabling auditing and cost control.
- **Deployment Security**: Docker Compose production mode with domain whitelist registration.

---

## Project Structure

```
backend/app/
  api/        # Route layer: parameter validation, auth, forwarding (no business logic)
  services/   # Business logic, single responsibility
  models/     # SQLAlchemy ORM models
  schemas/    # Pydantic request/response schemas
  core/       # Configuration, DB connection, auth middleware
  engine/     # [Single LLM exit] EngineProtocol + ClaudeCliEngine + CodexCliEngine
  storage/    # StorageProtocol + LocalStorage
  tasks/      # Background tasks: categorization worker, task status, and retries
infra/postgres/
  init.sql        # CREATE EXTENSION
  migrations/     # 001…041, executed automatically in order on startup
docs/             # PRD / DESIGN / ROADMAP / WORKFLOW / SECURITY
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [DESIGN.md](DESIGN.md) | Architecture design and API contracts |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Implementation roadmap and delivery records |
| [CLAUDE.md](CLAUDE.md) | Development conventions and hard prohibitions |
| [WORKFLOW.md](WORKFLOW.md) | Development protocol |
| [docs/SECURITY.md](docs/SECURITY.md) | Security threat model |

---

## Development Conventions

- All LLM calls go through `app/engine/` only; file access goes through `app/storage/` only.
- All document queries must include workspace permission filtering (prevent unauthorized access / IDOR).
- Secrets are not hard-coded; `storage_key` is server-generated to prevent path traversal.
- See [CLAUDE.md](CLAUDE.md) for details.

---

> May every conversation unlock the collective intelligence of your organization.
