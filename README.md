# LambChat

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/React-19-green.svg" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-Latest-orange.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/deepagents-Latest-purple.svg" alt="deepagents">
  <img src="https://img.shields.io/badge/MongoDB-Latest-green.svg" alt="MongoDB">
  <img src="https://img.shields.io/badge/Redis-Latest-red.svg" alt="Redis">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

English | [简体中文](README_CN.md)

> A production-ready AI Agent system built with FastAPI + deepagents

## 📸 Screenshots

### Main Interface

<table>
  <tr>
    <td align="center"><b>Login Page</b></td>
    <td align="center"><b>Chat Interface</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/login-page.png" alt="Login Page" width="400"/></td>
    <td><img src="docs/images/best-practice/chat-home.png" alt="Chat Interface" width="400"/></td>
  </tr>
  <tr>
    <td align="center"><b>Streaming Response</b></td>
    <td align="center"><b>Share Dialog</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/chat-response.png" alt="Streaming Response" width="400"/></td>
    <td><img src="docs/images/best-practice/share-dialog.png" alt="Share Dialog" width="400"/></td>
  </tr>
</table>

### Management Panels

<table>
  <tr>
    <td align="center"><b>Skills Management</b></td>
    <td align="center"><b>MCP Configuration</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/skills-page.png" alt="Skills Management" width="400"/></td>
    <td><img src="docs/images/best-practice/mcp-page.png" alt="MCP Configuration" width="400"/></td>
  </tr>
  <tr>
    <td align="center"><b>System Settings</b></td>
    <td align="center"><b>Feedback System</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/settings-page.png" alt="System Settings" width="400"/></td>
    <td><img src="docs/images/best-practice/feedback-page.png" alt="Feedback System" width="400"/></td>
  </tr>
  <tr>
    <td align="center"><b>Shared Session</b></td>
    <td align="center"><b>Role Management</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/shared-page.png" alt="Shared Session" width="400"/></td>
    <td><img src="docs/images/best-practice/roles-page.png" alt="Role Management" width="400"/></td>
  </tr>
</table>

### Responsive Design

<table>
  <tr>
    <td align="center"><b>Mobile View</b></td>
    <td align="center"><b>Tablet View</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/mobile-view.png" alt="Mobile View" width="250"/></td>
    <td><img src="docs/images/best-practice/tablet-view.png" alt="Tablet View" width="350"/></td>
  </tr>
</table>

## 🏗️ Architecture Overview

<p align="center">
  <img src="docs/images/best-practice/architecture.png" alt="LambChat Architecture" width="600"/>
</p>

## ✨ Features

### 🤖 Agent System
- **deepagents Architecture** - Compiled graph with fine-grained state management
- **Multi-Agent Types** - Core Agent (default), Fast Agent (optimized speed), Search Agent (web search)
- **Plugin System** - Register custom agents with `@register_agent("id")` decorator
- **Streaming Output** - Native SSE (Server-Sent Events) support
- **Sub-agents** - Multi-level agent nesting support
- **Thinking Mode** - Extended thinking mode for Anthropic models
- **Code Interpreter** - Built-in code execution with sandbox support
- **Human-in-the-Loop** - Approval system for sensitive operations

### 🔍 Web Search
- **Web Search Agent** - Search the web with rich results (title, URL, summary, site icon)
- **Domain Filtering** - Limit search results to specific domains
- **Time Range Filter** - Filter by day/week/month/year
- **Region Support** - Optimize for CN or US regions
- **Content Size Control** - Balanced (400-600 words) or comprehensive (2500 words) summaries

### 🔌 MCP Integration
- **System + User Level MCP** - Global and personal MCP server configs
- **Encrypted Storage** - Sensitive data like API keys are encrypted
- **Dynamic Caching** - Tool caching with manual refresh support
- **Multiple Transports** - Support for stdio, SSE, and HTTP transports
- **Permission Control** - Transport-level access permissions

### 🛠️ Skills System
- **Dual Storage** - File system + MongoDB backup
- **Access Control** - User-level skill permissions
- **GitHub Sync** - Sync custom skills from GitHub repositories
- **Skill Creator** - Built-in skill creation toolkit with evaluation tools
- **5 Skill Slots** - Enable up to 5 skills per session

### 💬 Feedback System
- **Thumbs Rating** - Simple positive/negative feedback
- **Text Comments** - Detailed user feedback
- **Session Linking** - Feedback tied to specific sessions/messages
- **Run-Level Stats** - Aggregate feedback statistics per run

### 📁 Document & File Support
- **Multi-format Preview** - PDF / Word / Excel / PPT / Markdown / Mermaid
- **Image Viewer** - Built-in image preview with zoom support
- **File Upload** - Drag & drop or click to upload multiple files
- **Cloud Storage** - S3 / OSS / MinIO integration
- **Folder Management** - Organize conversations into folders
- **Session Search** - Full-text search across all conversations

### 🔄 Real-time & Storage
- **Dual-write Mechanism** - Redis for real-time, MongoDB for persistence
- **WebSocket Support** - Real-time bidirectional communication
- **Auto Reconnect** - Resume conversation after disconnection
- **Session Sharing** - Share conversations with public or authenticated links

### 🔐 Security & Auth
- **JWT Authentication** - Complete auth flow with token refresh
- **RBAC Roles** - Admin / User / Guest levels
- **Password Encryption** - bcrypt hashing
- **OAuth Support** - Login with Google, GitHub, etc.
- **Email Verification** - Secure email-based account verification
- **Sandbox Execution** - Isolated code execution environment

### ⚙️ Task Management
- **Concurrency Control** - Task execution queue with concurrency limits
- **Cancellation** - Cancel running tasks
- **Heartbeat** - Task health monitoring
- **Pub/Sub** - Event-driven task notifications
- **Status Tracking** - Real-time task status updates

### 🔗 Channels & Integrations
- **Feishu (Lark)** - Native integration with Lark/Feishu platform
- **Multi-Channel** - Extensible channel system for messaging platforms
- **Email Service** - Built-in email notification support
- **Project Management** - Organize chats by projects

### 📊 Observability & Admin
- **LangSmith Tracing** - Optional LangSmith integration for agent tracing
- **Structured Logging** - Context-aware structured logging
- **Health Check** - API health and readiness endpoints
- **User Management** - View and manage users
- **Role Assignment** - Configure agent access per role

### 🎨 Frontend
- **Modern Stack** - React 19 + Vite + TailwindCSS
- **ChatGPT Style** - Familiar chat interface
- **Theme Support** - Dark/Light mode with smooth transitions
- **i18n** - Multi-language support (English, Chinese, Japanese, Korean)
- **Responsive Design** - Mobile, tablet, and desktop optimized
- **Agent Switcher** - Toggle between Core/Fast/Search agents

## ⚙️ Configuration

LambChat supports 14 setting categories, configurable via the Settings page or environment variables:

| Category | Description |
|----------|-------------|
| **Frontend** | Default agent, welcome suggestions, UI preferences |
| **Agent** | Debug mode, logging level |
| **LLM** | Model selection, temperature, max tokens, API key & base URL |
| **Session** | Session management settings |
| **Database** | MongoDB connection settings |
| **Long-term Storage** | Persistent storage configuration |
| **Security** | Security policies and encryption |
| **S3** | Cloud storage (S3/OSS) configuration |
| **Sandbox** | Code sandbox settings |
| **Skills** | Skill system configuration |
| **Tools** | Tool system settings |
| **Tracing** | LangSmith and tracing configuration |
| **User** | User management settings |
| **Memory** | Memory system (hindsight) settings |

## 🛠️ Development

### Prerequisites
- Python 3.12+
- Node.js 18+
- MongoDB
- Redis

### Quick Start

```bash
# Clone repository
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# Copy environment file
cp .env.example .env
# Edit .env with your configuration

# Start with Docker (recommended)
docker-compose up -d

# Or run locally
make install  # Install dependencies
make dev      # Start development server
```

Access the app at `http://localhost:8000`

### Code Quality

```bash
# Format code
ruff format src/

# Check style
ruff check src/

# Type check
mypy src/
```

### Project Structure

```
src/
├── agents/          # Agent implementations (core, fast, search)
├── api/             # FastAPI routes and middleware
├── infra/           # Infrastructure services
│   ├── auth/        # JWT authentication
│   ├── backend/     # Backend management
│   ├── channel/     # Multi-channel (Feishu, etc.)
│   ├── email/       # Email service
│   ├── feedback/    # Feedback system
│   ├── folder/      # Folder management
│   ├── llm/         # LLM integration
│   ├── memory/      # Memory & hindsight
│   ├── mcp/         # MCP protocol
│   ├── patches/     # Monkey patches and compat fixes
│   ├── role/        # RBAC role management
│   ├── sandbox/     # Sandbox execution
│   ├── session/     # Session management (dual-write)
│   ├── settings/    # Settings service
│   ├── share/       # Session sharing
│   ├── skill/       # Skills system
│   ├── storage/     # File storage
│   ├── task/        # Task management
│   ├── tool/        # Tool registry & MCP client
│   ├── tracing/     # LangSmith tracing
│   ├── user/        # User management
│   └── websocket/   # WebSocket support
├── kernel/          # Core schemas, config, types
└── skills/          # Built-in skills (skill-creator)
```

## 🤝 Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

[MIT](LICENSE)

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/Yanyutin753">Clivia</a>
</p>
