<div align="center">

# 🐑 LambChat

**An open-source, production-ready AI Agent platform for building, running, and sharing real tool-using agents**

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

## 🌟 Why LambChat

LambChat is built for teams who want more than a chatbot UI. It gives you a complete AI Agent system with model management, MCP connectivity, skills, storage, sharing, approvals, and deployment-ready backend/frontend infrastructure in one project.

- **Built for real execution** — agents can reason, call tools, use sub-agents, stream progress, and work with human approval when needed.
- **Ready for operations** — includes auth, RBAC, encrypted secrets, tracing, health checks, sandbox integration, and distributed config sync.
- **Designed for extensibility** — custom agents, MCP tools, skills, model providers, channels, persona presets, and storage backends can all be extended cleanly.
- **Product-grade UX** — polished chat UI, file previews, project folders, sharing, feedback, responsive layouts, and multilingual support.

## 🎬 Use Cases

| # | Case | Description | Demo |
|---|------|-------------|------|
| 1 | Supply Chain PDF Report | Generates a polished PDF efficiency report with charts, benchmark comparisons, and delivery, inventory, fulfillment, and logistics analysis from a single prompt. | [View Session](https://lambchat.com/shared/w0WA7GtMCyca) |
| 2 | Godfather Fan Website | Builds a responsive English promo site for *The Godfather* trilogy with a cinematic visual direction, marquee hero section, generated images, and multi-device polish. | [View Session](https://lambchat.com/shared/9XlmaDANCjO9) |
| 3 | Story Breakdown from Image | Understands visual input, identifies the stories shown in an image, and produces detailed plot-by-plot explanations with multimodal reasoning. | [View Session](https://lambchat.com/shared/MZX-eNnOoilN) |
| 4 | EV Market Trend Analysis | Turns recent 2025-2026 electric vehicle data into a structured market analysis covering growth, regional performance, and key industry takeaways. | [View Session](https://lambchat.com/shared/5XUeuDEyd2CY) |

## 🏗️ Architecture

<p align="center"><img src="docs/images/best-practice/architecture.webp" width="600" alt="Architecture"></p>

## ✨ Features

<details>
<summary><b>🤖 Agent Runtime</b></summary>

- **deepagents Architecture** — Compiled graph runtime with fine-grained state management
- **Multi-Agent Types** — Core, fast, and search agents
- **Plugin System** — `@register_agent("id")` decorator for custom agents
- **Streaming Output** — Native SSE support
- **Sub-agents** — Multi-level delegation
- **Thinking Mode** — Extended thinking for Anthropic models
- **Human-in-the-Loop** — Approval system with countdown timer, auto-extension, and urgent-state styling
- **Persona Presets** — Reusable persona configuration with permissions and runtime binding

</details>

<details>
<summary><b>🧠 Model, Memory, and Skills</b></summary>

- **Multi-Provider Models** — OpenAI, Anthropic, Google Gemini, and Kimi
- **Full CRUD** — Create, edit, delete, reorder, and batch import models via UI
- **Channel Routing** — Route the same model through different channels with `model_id`
- **Role-based Access** — `MODEL_ADMIN` permission and per-role model visibility
- **Cross-session Memory** — Native MongoDB-backed memory system
- **Dual Skills Storage** — File system plus MongoDB backup
- **GitHub Sync** — Import custom skills from GitHub
- **Skill Marketplace** — Browse, install, publish, and manage skills in bulk

</details>

<details>
<summary><b>🔌 Tools, MCP, and Execution</b></summary>

- **System + User MCP** — Global and per-user MCP configuration
- **Encrypted Storage** — API keys encrypted at rest
- **Dynamic Tool Caching** — Cache MCP tools with manual refresh
- **Multiple Transports** — SSE and HTTP
- **Permission Control** — Transport-level access policies
- **Sandbox Integration** — Daytona and E2B execution support
- **Built-in Tools** — File reveal, project reveal, upload URL, env vars, audio transcription, persona preset tools, and more

</details>

<details>
<summary><b>📁 Product Features</b></summary>

- **File Library** — Browse revealed files with code preview, favorites, and project-based filtering
- **Rich Previews** — PDF, Word, Excel, PPT, Markdown, Mermaid, Excalidraw, images, and video playback
- **Project Folders** — Organize sessions into projects with drag-and-drop
- **Session Sharing** — Generate public share links for conversations
- **Feedback** — Thumbs rating, text comments, session linking, and run-level stats
- **Notifications** — In-app notification storage and delivery hooks

</details>

<details>
<summary><b>🔐 Infra, Realtime, and Frontend</b></summary>

- **Realtime** — Redis + MongoDB dual-write, WebSocket, auto-reconnect, and shared-session updates
- **Security** — JWT, RBAC, bcrypt, OAuth (Google/GitHub/Apple), email verification, CAPTCHA, and sandbox controls
- **Observability** — LangSmith tracing, structured logging, health checks, and distributed memory diagnostics
- **Channels** — Native Feishu integration plus an extensible multi-channel architecture
- **Frontend Stack** — React 19, Vite 6, TailwindCSS 3.4, dark/light theme, rich content rendering, and responsive multi-device layouts
- **i18n** — English, Chinese, Japanese, Korean, and Russian

</details>

## ⚙️ Configuration

Multiple setting categories can be configured through the UI or environment variables:

| Category | Description |
|----------|-------------|
| Frontend | Default agent, welcome suggestions, UI preferences |
| Agent | Debug mode, logging level |
| Model | Multi-provider model management, per-model config, channel routing |
| Session | Session management, message history, SSE cache |
| Database | MongoDB connection, optional PostgreSQL |
| Storage | Persistent storage, S3/OSS/MinIO/COS |
| Security | Encryption and security policies |
| Sandbox | Code sandbox settings (Daytona / E2B) |
| Skills | Skill system config |
| Tools | Tool system settings |
| Tracing | LangSmith and tracing |
| User | User management, registration, default role |
| Memory | Memory system (native) |

## 🚀 Quick Start

### Prerequisites

- Python 3.12+ · Node.js 18+ · pnpm · MongoDB · Redis

### Setup

```bash
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# Docker (recommended)
cd deploy && cp .env.example .env   # Edit with your config
docker compose up -d

# Or local development
cp .env.example .env   # Edit with your config
make install-pnpm      # Install pnpm if not present
make install && make dev
```

Open **http://localhost:8000**

### Code Quality

```bash
make format       # Format (ruff format)
make lint         # Lint (ruff check)
make typecheck    # Type check (mypy)
make check-all    # Run all checks (lint + typecheck + test)
```

### Project Structure

```text
src/
├── agents/         # Agent implementations and runtime graphs
├── api/            # FastAPI routes, admin endpoints, middleware
├── infra/          # Core services: auth, llm, mcp, tools, storage, tasks, sharing, memory
├── kernel/         # Schemas, config, constants, and shared types
└── skills/         # Built-in skills
frontend/
├── src/components/ # UI components, panels, and landing sections
├── src/hooks/      # Frontend hooks
├── src/i18n/       # Locale files
└── src/styles/     # Shared styles and design tokens
tests/              # Backend and integration tests
deploy/             # Docker deployment assets
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

<sub><strong>LambChat</strong> is built for people who want AI agents that can actually do the work.</sub>

<br>

<strong>Created by <a href="https://github.com/Yanyutin753">Clivia</a></strong>

<br>

<a href="https://github.com/Yanyutin753">GitHub</a> · <a href="mailto:3254822118@qq.com">Email</a> · <a href="README_CN.md">中文 README</a>

<br><br>

<img src=".github/images/wechat-qr.webp" width="160" alt="WeChat QR Code">

<br>

<sub>WeChat for deployment help, product feedback, and collaboration</sub>

</div>
