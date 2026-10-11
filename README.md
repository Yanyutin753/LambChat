<div align="center">

# 🐑 LambChat

**Your personal AI agent, living in the cloud — open source, self-hosted, always on. Multi-tenant when you need it.**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)]()
[![React](https://img.shields.io/badge/React-19-green.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-orange.svg)]()
[![deepagents](https://img.shields.io/badge/deepagents-Latest-purple.svg)]()
[![MongoDB](https://img.shields.io/badge/MongoDB-Latest-green.svg)]()
[![Redis](https://img.shields.io/badge/Redis-Latest-red.svg)]()
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) · [简体中文](README_CN.md) · [Documentation](https://yanyutin753.github.io/LambChat/en/) · [Contributing](CONTRIBUTING.md)

<br>

<img src="docs/images/readme/hero.webp" alt="LambChat personal AI agent" width="920">

</div>

---

## Meet Your Agent

Most AI products are conversations that end when you close the tab. LambChat is a **personal agent you deploy once to your own cloud**. It stays online for you: it remembers your context across sessions, runs your choice of models, calls your MCP tools, executes real work in isolated sandboxes, and brings finished results — reports, websites, analyses, image sets — to every device, or straight into your IM. While you are away, scheduled tasks keep running and ping you when the work is done.

Because you host it, your keys, your memory, and your files stay yours.

## Solo Agent, or a Multi-Tenant Platform

The same deployment scales both ways:

| Just you | A whole team |
|---|---|
| <img src="docs/images/illustrations/lamb-avatar.webp" width="64" alt="Solo agent"><br>**You** | <img src="docs/images/illustrations/lamb-panel-team.webp" width="64" alt="Team platform"><br>**Your team** |
| One account, your memory, your skills, your keys — the agent works for you and remembers you. | Multi-user accounts with registration approval, OAuth sign-in, and RBAC roles. |
| Scheduled tasks and IM channels keep it working and reachable around the clock. | Per-role model visibility, user default models, shared sessions, feedback, and usage stats. |
| Every deliverable lands in your file library, kept and searchable. | Admins **batch-create models** and manage MCP servers once — everyone else just uses them. |

| If you want to... | Go here |
|---|---|
| See what the agent can do | [Product Preview](#product-preview) and [Live Examples](#live-examples) |
| Use it solo or with a team | [Solo Agent, or a Multi-Tenant Platform](#solo-agent-or-a-multi-tenant-platform) |
| Run it quickly | [Quick Start](#quick-start) |
| Understand the system | [Architecture](#architecture) and [How It Works](#how-it-works) |
| Configure production pieces | [Configuration](#configuration) and [Deployment](https://yanyutin753.github.io/LambChat/en/deploy/docker.html) |
| Contribute | [Development](#development) and [Contributing](CONTRIBUTING.md) |

## What Makes It a Personal Agent

| It remembers you | It uses your tools | It does real work | It reaches you |
|---|---|---|---|
| <img src="docs/images/illustrations/lamb-reading.webp" width="96" alt="The lamb remembers you"><br>**Remembers you** | <img src="docs/images/illustrations/lamb-welcome.webp" width="96" alt="The lamb with your tools"><br>**Your tools** | <img src="docs/images/illustrations/lamb-files.webp" width="96" alt="The lamb at work"><br>**Real work** | <img src="docs/images/illustrations/lamb-message.webp" width="96" alt="The lamb reaches you"><br>**Reaches you** |
| Cross-session memory, personas, and skills it accumulates over time — the agent knows you tomorrow, not just for this chat. | Multi-provider models, system/user MCP servers with encrypted secrets, rich web search — bring your own everything. | deepagents/LangGraph runtime with sub-agents, human approval, and sandboxed code execution that produces real deliverables. | Web, PWA, mobile, and desktop apps with realtime sync, plus Feishu/Lark, WeChat, Telegram, Slack, DingTalk, Discord, email, and more notification channels. |

## Product Preview

| Chat and execution | Skills marketplace | Model management |
|:---:|:---:|:---:|
| <img src="docs/images/best-practice/chat-response.webp" width="300" alt="Streaming agent response"><br>**Streaming agent work** | <img src="docs/images/best-practice/marketplace-page.webp" width="300" alt="Skill marketplace"><br>**Skills it accumulates** | <img src="docs/images/best-practice/models-page.webp" width="300" alt="Model configuration"><br>**Your models, your keys** |
| <img src="docs/images/best-practice/files-page.webp" width="300" alt="File library"><br>**Deliverables library** | <img src="docs/images/best-practice/mcp-page.webp" width="300" alt="MCP configuration"><br>**MCP tools** | <img src="docs/images/best-practice/mobile-view.webp" width="190" alt="Mobile responsive view"><br>**With you everywhere** |

<details>
<summary><b>View the full screenshot gallery</b></summary>

| | | |
|:---:|:---:|:---:|
| <img src="docs/images/best-practice/login-page.webp" width="280" alt="Login"><br>**Login** | <img src="docs/images/best-practice/register-page.webp" width="280" alt="Register"><br>**Register** | <img src="docs/images/best-practice/reset-request-page.webp" width="280" alt="Password Reset"><br>**Password Reset** |
| <img src="docs/images/best-practice/verify-email-page.webp" width="280" alt="Email Verification"><br>**Email Verification** | <img src="docs/images/best-practice/registration-pending-page.webp" width="280" alt="Registration Pending"><br>**Registration Pending** | <img src="docs/images/best-practice/chat-home.webp" width="280" alt="Chat"><br>**Chat** |
| <img src="docs/images/best-practice/chat-response.webp" width="280" alt="Streaming"><br>**Streaming** | <img src="docs/images/best-practice/share-dialog.webp" width="280" alt="Share"><br>**Share** | <img src="docs/images/best-practice/skills-page.webp" width="280" alt="Skills"><br>**Skills** |
| <img src="docs/images/best-practice/marketplace-page.webp" width="280" alt="Marketplace"><br>**Marketplace** | <img src="docs/images/best-practice/mcp-page.webp" width="280" alt="MCP"><br>**MCP Config** | <img src="docs/images/best-practice/agents-page.webp" width="280" alt="Agents"><br>**Agents** |
| <img src="docs/images/best-practice/models-page.webp" width="280" alt="Models"><br>**Models** | <img src="docs/images/best-practice/channels-page.webp" width="280" alt="Channels"><br>**Channels** | <img src="docs/images/best-practice/files-page.webp" width="280" alt="Files"><br>**Files** |
| <img src="docs/images/best-practice/persona-page.webp" width="280" alt="Persona"><br>**Persona** | <img src="docs/images/best-practice/memory-page.webp" width="280" alt="Memory"><br>**Memory** | <img src="docs/images/best-practice/notifications-page.webp" width="280" alt="Notifications"><br>**Notifications** |
| <img src="docs/images/best-practice/settings-page.webp" width="280" alt="Settings"><br>**Settings** | <img src="docs/images/best-practice/feedback-page.webp" width="280" alt="Feedback"><br>**Feedback** | <img src="docs/images/best-practice/shared-page.webp" width="280" alt="Shared"><br>**Shared Session** |
| <img src="docs/images/best-practice/roles-page.webp" width="280" alt="Roles"><br>**Roles** | <img src="docs/images/best-practice/users-page.webp" width="280" alt="Users"><br>**Users** | <img src="docs/images/best-practice/tablet-view.webp" width="280" alt="Tablet"><br>**Tablet** |

</details>

## Live Examples

These shared sessions show the kind of end-to-end work your agent does — each one finished with a real deliverable, not a chat transcript.

| # | Case | What the agent does | Demo |
|---|---|---|---|
| 1 | Supply Chain PDF Report | Generates a polished PDF efficiency report with charts, benchmark comparisons, and delivery, inventory, fulfillment, and logistics analysis from a single prompt. | [View Session](https://lambchat.com/shared/w0WA7GtMCyca) |
| 2 | Godfather Fan Website | Builds a responsive English promo site for *The Godfather* trilogy with a cinematic visual direction, marquee hero section, generated images, and multi-device polish. | [View Session](https://lambchat.com/shared/9XlmaDANCjO9) |
| 3 | Story Breakdown from Image | Understands visual input, identifies the stories shown in an image, and produces detailed plot-by-plot explanations with multimodal reasoning. | [View Session](https://lambchat.com/shared/MZX-eNnOoilN) |
| 4 | EV Market Trend Analysis | Turns recent 2025-2026 electric vehicle data into a structured market analysis covering growth, regional performance, and key industry takeaways. | [View Session](https://lambchat.com/shared/5XUeuDEyd2CY) |
| 5 | Batch Game UI Icon Generation | Analyzes one reference image, generates **48 game UI icons** across 9 categories, organizes them into folders, and saves the workflow as a reusable skill. | [View Session](https://lambchat.com/shared/IsLxtk1RJ7wn) |
| 6 | E-Commerce Product Image Suite | Runs audience analysis, visual strategy, main image generation, lifestyle scenes, detail shots, and combo images for a product keyword and marketplace. | [View Session](https://lambchat.com/shared/wgs2zatzGi_2) |
| 7 | Multi-Agent E-Commerce Design Team | **4 agents collaborate** (creative director, designer, AI image engineer, reviewer) to produce a full set of brand e-commerce product images with strategy, generation, audit, and revision in one session. | [View Session](https://lambchat.com/shared/e6OCDGkrpgU1) |
| 8 | Daily AI Paper Digest (Scheduled Task) | A **scheduled task** runs automatically every day — no one at the keyboard — to search arXiv across 5 research directions (VLA, World Models, LLM Reasoning, Multimodal, Agent), filter the latest papers, and generate a structured trend summary. | [View Session](https://lambchat.com/shared/G-uQf_O-wXnQ) |

## How It Works

<details open>
<summary><b>A runtime that finishes work</b></summary>

- **deepagents architecture** with compiled graph runtime and fine-grained state management.
- **Multiple agent types** for core, fast, search, and team workflows — a team of agents can split a job and hand work to each other.
- **Plugin registration** through `@register_agent("id")` for custom agents.
- **Streaming output** with native SSE — watch the agent think, call tools, and write, live.
- **Sub-agents** for multi-level delegation.
- **Thinking mode** for extended reasoning.
- **Human approval** with countdown timer and auto-extension when the agent needs your sign-off.
- **`/goal` command** — attach a rubric-guided objective to any run via `/goal <objective>`, with optional custom rubrics (`/goal <objective> --- <rubric>`), SSE event tracking, and auto-dismissal on completion.

</details>

<details open>
<summary><b>It remembers you</b></summary>

- **Cross-session memory** backed by MongoDB — preferences, projects, and lessons persist across chats and devices.
- **Persona presets** with reusable configuration, permissions, and runtime binding.
- **Skills it accumulates** — package a workflow once (like the 48-icon batch above) and the agent reuses it forever: dual storage, access control, GitHub sync, marketplace publishing, and authoring tools.

</details>

<details open>
<summary><b>Your models, your keys</b></summary>

- **Multi-provider models** for OpenAI, Anthropic, Google Gemini, Kimi, and more — configured in the UI, stored encrypted, no `.env` key juggling.
- **Model CRUD** with batch creation — create many models in one pass, then edit, reorder, or remove them.
- **Channel routing** to reuse the same model through different channels with `model_id`.
- **Fallback models** so a run survives a provider outage.
- **Role-based model access** through `MODEL_ADMIN` and per-role visibility — batch-create models as an admin, expose only what each role should see.

</details>

<details open>
<summary><b>Tools, MCP, and sandboxed execution</b></summary>

- **System and user MCP servers** — connect the tools you already use, with encrypted secrets at rest, dynamic tool caching, SSE/HTTP transports, import/export, and tool-level access control.
- **Rich web search** with domain filtering, time range, region support, and content size control.
- **Sandboxed execution** in Daytona, E2B, or CubeSandbox — or a local sandbox daemon for desktop clients — so the agent can write and run real code safely.
- **Built-in tools** for file reveal, project reveal, upload URLs, env vars, audio transcription, persona presets, and more.

</details>

<details open>
<summary><b>Always on, always reachable</b></summary>

- **Scheduled tasks** with cron, interval, date, and manual triggers, persisted scheduler state, concurrency control, cancellation, and heartbeat monitoring — the agent works while you sleep.
- **Notification channels** for Feishu/Lark, WeChat, WeCom, Telegram, Slack, DingTalk, Discord, Bark, Pushover, ntfy, Gotify, email, and generic webhooks — results arrive where you already are.
- **Realtime sync** with Redis + MongoDB dual-write, WebSocket updates, auto-reconnect, and shared-session updates — pick up any device mid-run.
- **Every client** — React 19 web with PWA, Capacitor Android/iOS apps, and Tauri desktop builds, in five languages with dark/light themes.

</details>

<details open>
<summary><b>Deliverables, not chat bubbles</b></summary>

- **File library** with revealed files, code preview, favorites, and project filters — everything the agent produces is kept and browsable.
- **Rich previews** for PDF, Word, Excel, PPT, Markdown, Mermaid, Excalidraw, images, and video.
- **Project folders** for organizing sessions with drag-and-drop.
- **Session sharing** through public conversation links.
- **Feedback loop** with thumbs rating, comments, session links, and run-level stats.

</details>

<details open>
<summary><b>Safe by default</b></summary>

- **Security** with JWT, RBAC, bcrypt, OAuth, email verification, CAPTCHA, and sandbox execution boundaries.
- **Observability** with LangSmith tracing, structured logging, health checks, and distributed memory diagnostics.
- **Task runtime** with local execution or Redis-backed arq queues.

</details>

## Architecture

<p align="center"><img src="docs/images/best-practice/architecture.webp" width="680" alt="LambChat architecture"></p>

One deployable system, no external SaaS required: a FastAPI backend with LangGraph/deepagents execution, Redis/MongoDB persistence, and sandbox isolation, behind a React 19 workspace.

- **Frontend**: React 19, Vite, TailwindCSS, PWA workers, Capacitor mobile builds, and Tauri desktop packaging.
- **Backend**: FastAPI, SSE/WebSocket streaming, auth/RBAC, scheduler, storage services, model routing, and MCP management.
- **Agent runtime**: deepagents/LangGraph execution, sub-agents, approvals, skills, memory, tools, and sandbox integrations.
- **Persistence and queues**: MongoDB, Redis, optional PostgreSQL checkpoints, S3-compatible object storage, and arq workers.

| | | |
|:---:|:---:|:---:|
| **14+** setting categories | **3** agent types | **5** languages |
| **3+** OAuth providers | **SSE** streaming output | **15+** notification channels |

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Node.js 18+
- [pnpm](https://pnpm.io/) 10+
- MongoDB
- Redis

### Docker (Recommended)

```bash
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

cd deploy
cp .env.example .env
docker compose up -d
```

Open **http://localhost:8000**.

### Local Development

Install dependencies:

```bash
cp .env.example .env
make install-all
```

Run the backend and frontend together:

```bash
make dev-all
```

Backend: **http://127.0.0.1:8000**
Frontend dev server: **http://127.0.0.1:3001**

You can also run them separately:

```bash
make dev            # FastAPI backend: uv run python main.py
make frontend-dev   # Vite frontend
```

> LLM models are configured through the **Model Config UI** after deployment. You do not need to put model keys in environment variables for the basic boot path.

Connect your models, MCP servers, skills, and IM channels — then let your agent get to work.

## Configuration

LambChat can be configured through the UI and environment variables. Start with `.env.example`, then set stable secrets before using it with real users.

Runtime settings stored in the database take precedence over environment variables. Environment variables are used as initial values or fallback values only when the corresponding database setting has not been set.

```bash
# Recommended: keep sessions valid across restarts
JWT_SECRET_KEY=your-stable-secret-key

# Recommended: keep saved MCP configs decryptable across restarts
MCP_ENCRYPTION_SALT=your-stable-encryption-salt

# Optional: MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB=agent_state
MONGODB_USERNAME=admin
MONGODB_PASSWORD=your-mongo-password

# Optional: Redis
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=your-redis-password

# Optional: scheduled tasks
ENABLE_SCHEDULED_TASK=true

# Optional: task execution backend
TASK_BACKEND=arq  # local or arq
```

| Category | What it controls |
|---|---|
| Frontend | Default agent, welcome suggestions, UI preferences |
| Agent | Debug mode, logging level |
| Model | Multi-provider model management, per-model config, channel routing |
| Session | Session management, message history, SSE cache |
| Database | MongoDB connection, optional PostgreSQL |
| Storage | Persistent storage, S3/OSS/MinIO/COS |
| Security | Encryption and security policies |
| Sandbox | Code sandbox settings for Daytona, E2B, and CubeSandbox |
| Skills | Skill system configuration |
| Tools | Tool system settings |
| Tracing | LangSmith and tracing |
| User | User management, registration, default role |
| Memory | Native memory system |
| Scheduler | Dynamic scheduled tasks and runtime registration |
| Task Runtime | Local execution or arq queue settings |

## Development

### Code Quality

```bash
make format       # Format with ruff
make lint         # Lint with ruff
make typecheck    # Type check with mypy
make test         # Frontend (vitest) + backend (pytest) tests
make check-all    # Run pre-commit hooks + typecheck + tests + builds
```

### Frontend, Mobile, and Docs

```bash
cd frontend
pnpm run build             # TypeScript + Vite build
pnpm run packaged:build    # Build packaged frontend assets
pnpm run mobile:sync       # Build and sync Capacitor projects
pnpm run package:desktop   # Package desktop app assets

cd ..
pnpm run docs:dev          # VitePress docs site
pnpm run docs:build
```

### Project Structure

```text
.
├── main.py                  # Uvicorn entrypoint for src.api.main:app
├── src/
│   ├── agents/              # Core, fast, search, and team agent graphs
│   ├── api/                 # FastAPI app, middleware, and route modules
│   │   └── routes/          # Chat, auth, MCP, skills, files, scheduler, teams, etc.
│   ├── infra/               # Runtime services: auth, llm, mcp, scheduler, task, storage, memory
│   └── kernel/              # Settings, schemas, config definitions, and shared types
├── frontend/
│   ├── src/                 # React app source
│   │   ├── components/      # Chat, panels, pages, auth, skill, MCP, team, file UI
│   │   ├── services/        # API clients and browser service integrations
│   │   ├── stores/          # Frontend state stores
│   │   ├── i18n/            # Locale files and tests
│   │   └── workers/         # Browser/PWA workers
│   ├── android/             # Capacitor Android project
│   ├── ios/                 # Capacitor iOS project
│   ├── src-tauri/           # Tauri desktop shell
│   └── scripts/             # Frontend build, packaging, and i18n scripts
├── docs/                    # VitePress documentation
├── deploy/                  # Docker Compose deployment
├── k8s/                     # Kubernetes manifests
├── nginx/                   # Reverse proxy config
├── scripts/                 # Sandbox and maintenance utilities
└── tests/                   # Backend, API, infra, agent, and unit tests
```

## Star History

<div align="center">

<a href="https://star-history.com/#Yanyutin753/LambChat&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date" />
 </picture>
</a>

</div>

## Contributors

<div align="center">

<a href="https://github.com/Yanyutin753/LambChat/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Yanyutin753/LambChat" alt="Contributors">
</a>

</div>

## License

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

> **Note** — The project name **"LambChat"** and its logo may not be changed or removed.

---

<div align="center">

<h3>🐑 LambChat</h3>

<p><em>Deploy it once. It works for you — anywhere, anytime.</em></p>

<br>

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/Yanyutin753/LambChat">
        <img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"><br>
        <sub>Repository</sub>
      </a>
    </td>
    <td align="center">
      <a href="mailto:3254822118@qq.com">
        <img src="https://img.shields.io/badge/Email-D14836?style=for-the-badge&logo=gmail&logoColor=white" alt="Email"><br>
        <sub>Contact</sub>
      </a>
    </td>
    <td align="center">
      <a href="https://yanyutin753.github.io/LambChat/en/">
        <img src="https://img.shields.io/badge/Docs-0080FF?style=for-the-badge&logo=gitbook&logoColor=white" alt="Docs"><br>
        <sub>Documentation</sub>
      </a>
    </td>
    <td align="center">
      <a href="README_CN.md">
        <img src="https://img.shields.io/badge/中文-README-ED1C24?style=for-the-badge&logo=readme&logoColor=white" alt="中文 README"><br>
        <sub>中文 README</sub>
      </a>
    </td>
  </tr>
</table>

<br>

<img src=".github/images/wechat-qr.webp" width="160" alt="WeChat QR Code">

<br>

<sub>💬 WeChat for deployment help, product feedback, and collaboration</sub>

<br>

</div>
