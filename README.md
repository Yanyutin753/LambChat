# LambChat

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/React-19-green.svg" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-Latest-orange.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-Latest-purple.svg" alt="LangGraph">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

English | [简体中文](README_CN.md)

> A production-ready AI Agent system built with FastAPI + LangGraph

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

## ✨ Features

### 🤖 Agent System
- **LangGraph Architecture** - Compiled graph with fine-grained state management
- **Plugin System** - Register custom agents with `@register_agent("id")` decorator
- **Streaming Output** - Native SSE (Server-Sent Events) support
- **Sub-agents** - Multi-level agent nesting support

### 🔌 MCP Integration
- **System + User Level MCP** - Global and personal MCP server configs
- **Encrypted Storage** - Sensitive data like API keys are encrypted
- **Dynamic Caching** - Tool caching with manual refresh support

### 🛠️ Skills System
- **Dual Storage** - File system + MongoDB backup
- **Access Control** - User-level skill permissions
- **GitHub Sync** - Sync custom skills from GitHub repositories

### 💬 Feedback System
- **Thumbs Rating** - Simple positive/negative feedback
- **Text Comments** - Detailed user feedback
- **Session Linking** - Feedback tied to specific sessions/messages

### 🔐 Security
- **JWT Authentication** - Complete auth flow
- **RBAC Roles** - Admin / User / Guest levels
- **Multi-tenancy** - Tenant-level resource isolation
- **Password Encryption** - bcrypt hashing

### 🎨 Frontend
- **Modern Stack** - React 19 + Vite + TailwindCSS
- **ChatGPT Style** - Familiar chat interface
- **Document Preview** - PDF / Word / Excel / PPT / Markdown / Mermaid
- **Theme Support** - Dark/Light mode
- **i18n** - Multi-language support

### ⚡ Real-time & Storage
- **Dual-write Mechanism** - Redis for real-time, MongoDB for persistence
- **Auto Reconnect** - Resume conversation after disconnection
- **S3/OSS Support** - Cloud storage integration

## 🚀 Quick Start

```bash
# Clone repository
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# Copy environment file
cp .env.example .env

# Start with Docker
docker-compose up -d

# Or run locally
make install  # Install dependencies
make dev      # Start development server
```

Access the app at `http://localhost:8000`

## 📄 License

[MIT](LICENSE)

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/Yanyutin753">Clivia</a>
</p>
