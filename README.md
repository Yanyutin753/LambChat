<div align="center">

# 🐑 LambChat

**A production-ready AI Agent system built with FastAPI + deepagents**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)]()
[![React](https://img.shields.io/badge/React-19-green.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-orange.svg)]()
[![deepagents](https://img.shields.io/badge/deepagents-Latest-purple.svg)]()
[![MongoDB](https://img.shields.io/badge/MongoDB-Latest-green.svg)]()
[![Redis](https://img.shields.io/badge/Redis-Latest-red.svg)]()
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) · [简体中文](README_CN.md) · [Contributing](CONTRIBUTING.md)

</div>

---

## 📸 Screenshots

| | | |
|:---:|:---:|:---:|
| <img src="docs/images/best-practice/login-page.webp" width="280" alt="Login"><br>**Login** | <img src="docs/images/best-practice/chat-home.webp" width="280" alt="Chat"><br>**Chat** | <img src="docs/images/best-practice/chat-response.webp" width="280" alt="Streaming"><br>**Streaming** |
| <img src="docs/images/best-practice/skills-page.webp" width="280" alt="Skills"><br>**Skills** | <img src="docs/images/best-practice/mcp-page.webp" width="280" alt="MCP"><br>**MCP Config** | <img src="docs/images/best-practice/share-dialog.webp" width="280" alt="Share"><br>**Share** |
| <img src="docs/images/best-practice/roles-page.webp" width="280" alt="Roles"><br>**Roles** | <img src="docs/images/best-practice/settings-page.webp" width="280" alt="Settings"><br>**Settings** | <img src="docs/images/best-practice/feedback-page.webp" width="280" alt="Feedback"><br>**Feedback** |
| <img src="docs/images/best-practice/mobile-view.webp" width="200" alt="Mobile"><br>**Mobile** | <img src="docs/images/best-practice/tablet-view.webp" width="280" alt="Tablet"><br>**Tablet** | <img src="docs/images/best-practice/shared-page.webp" width="280" alt="Shared"><br>**Shared Session** |

## 🎬 Use Cases

| # | Case | Description | Demo |
|---|------|-------------|------|
| 1 | PDF Report Generation | Agent reads skill instructions → installs dependencies → generates 8 charts → writes LaTeX source → compiles into a 14-page PDF business report. Zero human intervention. | [View Session](https://lambchat.com/shared/Yaotot5Fav8j) |
| 2 | PPT Presentation | Agent independently creates a 14-page business PPT with data tables, charts, analysis cards, and action roadmap based on supply chain data. | [View Session](https://lambchat.com/shared/VOjediSYBHR1) |
| 3 | Static Blog Site | Builds a complete blog (5 pages + 8 sample articles) with tag filtering, pagination, responsive layout, and interactive effects. 10 subtasks all completed automatically. | [View Session](https://lambchat.com/shared/NuzvONPqCZLU) |

## 🏗️ Architecture

<p align="center"><img src="docs/images/best-practice/architecture.webp" width="600" alt="Architecture"></p>

## ✨ Features

<details>
<summary><b>🤖 Agent System</b></summary>

- **deepagents Architecture** — Compiled graph with fine-grained state management
- **Multi-Agent Types** — Core / Fast / Search agents
- **Plugin System** — `@register_agent("id")` decorator for custom agents
- **Streaming Output** — Native SSE support
- **Sub-agents** — Multi-level nesting
- **Thinking Mode** — Extended thinking for Anthropic models
- **Human-in-the-Loop** — Approval system with countdown timer, auto-extension, and urgent state styling

</details>

<details>
<summary><b>🧠 Model Management</b></summary>

- **Multi-Provider** — OpenAI, Anthropic, Google Gemini, Kimi (Moonshot)
- **Full CRUD** — Create, edit, delete, batch import models via UI with per-model config (api_key, api_base, temperature, max_tokens)
- **Channel Routing** — Same model from multiple channels via `model_id` routing
- **Role-based Access** — `MODEL_ADMIN` permission, per-role model visibility control
- **Per-user Preferences** — Default model selection persists across sessions
- **Live Config Sync** — Distributed Redis pub/sub for real-time model updates
- **Drag-and-Drop** — Reorder models in the selector

</details>

<details>
<summary><b>🔌 MCP Integration</b></summary>

- **System + User Level** — Global and per-user MCP configs
- **Encrypted Storage** — API keys encrypted at rest
- **Dynamic Caching** — Tool caching with manual refresh
- **Multiple Transports** — SSE / HTTP
- **Permission Control** — Transport-level access control
- **Import/Export** — Bulk MCP configuration management

</details>

<details>
<summary><b>🛠️ Skills System</b></summary>

- **Dual Storage** — File system + MongoDB backup
- **Access Control** — User-level permissions
- **GitHub Sync** — Import skills from GitHub repos
- **Skill Creator** — Built-in creation toolkit with evaluation tools
- **Marketplace** — Browse, install, and publish skills
- **Batch Operations** — Enable/disable/delete skills in bulk

</details>

<details>
<summary><b>💬 Feedback · 📁 Files · 🔄 Realtime · 🔐 Auth · ⚙️ Tasks · 📊 Observability</b></summary>

- **Feedback** — Thumbs rating, text comments, session-linked, run-level stats
- **File Library** — Browse revealed files, code preview, organized file management with grid/list views, favorites, and project-based filtering
- **Documents** — PDF / Word / Excel / PPT / Markdown / Mermaid / Excalidraw preview + image viewer
- **Cloud Storage** — S3 / OSS / MinIO / COS integration, drag & drop upload, presigned URLs
- **Project Folders** — Organize sessions into projects with drag-and-drop
- **Session Sharing** — Generate public share links for conversations
- **Realtime** — Dual-write (Redis + MongoDB), WebSocket, auto-reconnect, session sharing
- **Security** — JWT, RBAC (35+ permissions across 15 groups), bcrypt, OAuth (Google/GitHub/Apple), email verification, CAPTCHA, sandbox
- **Tasks** — Concurrency control, cancellation, heartbeat, pub/sub notifications
- **Observability** — LangSmith tracing, structured logging, health checks
- **Channels** — Feishu (Lark) native integration with model selector, project binding, and time-based session titles; extensible multi-channel system

</details>

<details>
<summary><b>🎨 Frontend</b></summary>

- **React 19 + Vite 6 + TailwindCSS 3.4**
- **ChatGPT-style** interface with dark/light theme
- **Glass Design System** — Consistent glass-shell/glass-card styling across all panels
- **i18n** — English, Chinese, Japanese, Korean, Russian
- **Responsive** — Mobile, tablet, desktop with unified component rendering
- **Rich Content** — KaTeX math, syntax highlighting, Mermaid diagrams, table copy/CSV export, image preview lightbox, line-highlighted code viewer
- **Tool Panels** — Slide-up tool result panels with center/sidebar view modes and block preview portal
- **Skeleton Loading** — Skeleton components for better perceived performance
- **Landing Page** — Premium blog-style landing with scroll-reveal animations and section tracking

</details>

## ⚙️ Configuration

14+ setting categories configurable via UI or environment variables:

| Category | Description |
|----------|-------------|
| Frontend | Default agent, welcome suggestions, UI preferences |
| Agent | Debug mode, logging level |
| Model | Multi-provider model management, per-model config, channel routing |
| Session | Session management, message history, SSE cache |
| Database | MongoDB connection, optional PostgreSQL |
| Storage | Persistent storage, S3/OSS/MinIO/COS |
| Security | Encryption & security policies |
| Sandbox | Code sandbox settings (Daytona / E2B) |
| Skills | Skill system config |
| Tools | Tool system settings |
| Tracing | LangSmith & tracing |
| User | User management, registration, default role |
| Memory | Memory system (native / hindsight / memu) |

## 🚀 Quick Start

### Prerequisites

- Python 3.12+ · Node.js 18+ · MongoDB · Redis

### Setup

```bash
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# Docker (recommended)
cd deploy && cp .env.example .env   # Edit with your config
docker compose up -d

# Or local development
cp .env.example .env   # Edit with your config
make install && make dev
```

→ Open **http://localhost:8000**

### Code Quality

```bash
ruff format src/    # Format
ruff check src/     # Lint
mypy src/           # Type check
```

### Project Structure

```
src/
├── agents/          # Agent implementations (core, fast, search)
├── api/             # FastAPI routes & middleware
│   ├── routes/      # 27 route modules (auth, chat, mcp, skills, model, etc.)
│   ├── admin/       # Admin API endpoints
│   └── agent/       # Agent configuration & model management
├── infra/           # Infrastructure services
│   ├── agent/       # Agent config & events
│   ├── auth/        # JWT, OAuth, RBAC, CAPTCHA
│   ├── backend/     # LLM backend abstraction
│   ├── channel/     # Multi-channel (Feishu, etc.)
│   ├── email/       # Email service (Resend)
│   ├── envvar/      # User environment variables
│   ├── feedback/    # Feedback system
│   ├── folder/      # Project folder management
│   ├── llm/         # LLM integration (OpenAI, Anthropic, Gemini, Kimi)
│   ├── memory/      # Cross-session memory (native, hindsight, memu)
│   ├── model/       # Model management with encryption & pub/sub sync
│   ├── mcp/         # MCP protocol
│   ├── role/        # RBAC roles
│   ├── sandbox/     # Sandbox execution (Daytona / E2B)
│   ├── session/     # Session management (dual-write)
│   ├── settings/    # Settings storage + pub/sub sync
│   ├── share/       # Share links
│   ├── skill/       # Skills system
│   ├── storage/     # MongoDB, Redis, PostgreSQL, S3
│   ├── task/        # Task management
│   ├── tool/        # Tool registry & MCP client
│   ├── tracing/     # LangSmith tracing
│   ├── upload/      # File upload handling
│   ├── revealed_file/  # File library
│   └── websocket/   # WebSocket & rate limiter
├── kernel/          # Core schemas, config, types
└── skills/          # Built-in skills
```

## ⭐ Star History

<a href="https://star-history.com/#Yanyutin753/LambChat&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date" />
 </picture>
</a>

## 📄 License

[MIT](LICENSE) — Project name "LambChat" and its logo may not be changed or removed.

---

<div align="center">

Made with ❤️ by [Clivia](https://github.com/Yanyutin753)

[📧 3254822118@qq.com](mailto:3254822118@qq.com) · [GitHub](https://github.com/Yanyutin753)

</div>
