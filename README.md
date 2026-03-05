# LambChat

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/React-19-green.svg" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-Latest-orange.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-Latest-purple.svg" alt="LangGraph">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

> 基于 FastAPI + LangGraph 构建的生产级 AI Agent 系统，提供完整的对话智能体能力

## 📌 项目简介

LambChat 是一个功能完备的 AI Agent 对话系统，采用现代化的微服务架构设计。系统支持流式输出、多模态文档处理、MCP 工具集成、用户反馈收集等企业级特性，适用于智能客服、知识库问答、AI 助手等多种场景。

## ✨ 核心特性

### 🤖 LangGraph Agent 架构

- **编译图架构**: 每个 Agent 都是一个 `CompiledGraph`，支持细粒度的状态管理和流程控制
- **装饰器注册**: 使用 `@register_agent("agent_id")` 快速注册自定义 Agent
- **工厂单例模式**: Agent 工厂统一管理所有 Agent 实例，支持热插拔
- **流式输出**: 原生支持 Server-Sent Events (SSE) 流式响应

```python
@register_agent("search_agent")
def create_search_agent():
    return compiled_graph
```

### 🎯 统一事件系统 (Presenter)

- **丰富的事件类型**: 文本、思考过程、工具调用、子 Agent、代码块、文件操作、人工审批
- **层级深度**: 支持主 Agent / 子 Agent 多层级嵌套
- **实时推送**: 基于 SSE 的实时事件推送

### ⚡ 双写机制

- **Redis**: 实时写入，SSE 低延迟推送
- **MongoDB**: 批量缓冲，按 trace_id 聚合，确保数据不丢失
- **断线重连**: 支持客户端断线重连，自动恢复对话上下文

### 🔌 MCP 集成

- **系统级 + 用户级 MCP 配置**: 支持全局和用户个人 MCP 服务器
- **敏感信息加密**: API Keys 等敏感信息加密存储
- **动态缓存**: MCP 工具缓存管理，支持手动刷新

### 🛠️ Skills 系统

- **双存储**: 文件系统 + MongoDB 双存储备份
- **访问控制**: 用户级别技能访问控制
- **GitHub 同步**: 支持从 GitHub 同步自定义 Skills

### 💬 用户反馈系统

- **评分机制**: 支持 thumbs up/down 简单反馈
- **详细评论**: 用户可添加文字评论
- **会话关联**: 反馈与具体会话/消息关联
- **可视化面板**: 独立反馈查看面板

### 🔐 权限与安全

- **JWT 认证**: 完整的 JWT 认证流程
- **RBAC 角色**: Admin / User / Guest 三级角色
- **多租户隔离**: 租户级别的资源隔离
- **密码加密**: bcrypt 密码加密

### 🎨 前端特性

- **现代 UI**: React 19 + Vite + TailwindCSS
- **ChatGPT 风格**: 熟悉的对话界面体验
- **多文档预览**: PDF / Word / Excel / PPT / Markdown / Mermaid
- **主题切换**: 深色/浅色主题支持
- **国际化**: i18n 多语言支持

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│  React 19 + Vite + TailwindCSS + TypeScript                │
│  - Chat Interface                                           │
│  - Document Viewer                                          │
│  - Admin Panel                                              │
└───────────────────────┬─────────────────────────────────────┘
                        │ REST API + SSE
┌───────────────────────▼─────────────────────────────────────┐
│                        Backend                               │
│  FastAPI + LangGraph + LangChain                            │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │   Agents    │ │   Tools     │ │   Storage   │          │
│  │ - Search    │ │ - MCP       │ │ - Redis     │          │
│  │ - Writer    │ │ - Skills    │ │ - MongoDB   │          │
│  │ - Custom    │ │ - Human     │ │ - S3/OSS    │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### 前置要求

- Python 3.12+
- Node.js 18+
- Redis
- MongoDB

### 安装部署

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/LambChat.git
cd LambChat

# 2. 安装后端依赖
make install

# 3. 安装前端依赖
make frontend-install

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置以下关键变量:
# LLM_API_KEY=your_api_key
# LLM_MODEL=anthropic/claude-3-5-sonnet-20241022
# MONGODB_URL=mongodb://localhost:27017
# REDIS_URL=redis://localhost:6379

# 5. 启动开发服务
make dev-all
```

### 服务地址

| 服务 | 地址 |
|------|------|
| API 文档 | http://localhost:8000/docs |
| 前端 | http://localhost:5173 |
| Redis | localhost:6379 |
| MongoDB | localhost:27017 |

## 📖 API 接口

### 认证接口

```bash
# 用户注册
POST /api/auth/register
{
  "username": "user@example.com",
  "password": "password123",
  "nickname": "User Name"
}

# 用户登录
POST /api/auth/login
{
  "username": "user@example.com",
  "password": "password123"
}
```

### 聊天接口

```bash
# 创建聊天会话
POST /api/chat/sessions

# 发送消息 (SSE 流式)
POST /api/chat/stream
{
  "session_id": "session_xxx",
  "message": "帮我搜索..."
}

# 获取历史消息
GET /api/chat/sessions/{session_id}/messages

# SSE 流式回放
GET /api/chat/sessions/{session_id}/stream
```

### Skills 接口

```bash
# 获取技能列表
GET /api/skills

# 同步 GitHub Skills
POST /api/skills/sync-github

# 创建/更新 Skill
POST /api/skills

# 删除 Skill
DELETE /api/skills/{skill_id}
```

### MCP 接口

```bash
# 获取 MCP 服务器列表
GET /api/mcp/servers

# 添加 MCP 服务器
POST /api/mcp/servers
{
  "name": "my-mcp",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
  "env": {}
}

# 删除 MCP 服务器
DELETE /api/mcp/servers/{server_id}

# 刷新 MCP 缓存
POST /api/mcp/refresh
```

### 反馈接口

```bash
# 提交反馈
POST /api/feedback
{
  "session_id": "session_xxx",
  "message_id": "msg_xxx",
  "rating": "positive",  # positive / negative
  "comment": "回答很好"
}

# 获取反馈列表 (Admin)
GET /api/feedback?page=1&page_size=20
```

### 文件接口

```bash
# 上传文件
POST /api/upload
Content-Type: multipart/form-data

# 获取文件类型
GET /api/file-type

# 获取预览 URL
GET /api/share/{share_id}
```

### 用户接口

```bash
# 获取当前用户信息
GET /api/user/me

# 更新用户设置
PUT /api/user/settings
{
  "theme": "dark",
  "language": "zh-CN"
}
```

## 📁 项目结构

```
LambChat/
├── src/                          # 后端源码
│   ├── api/                      # API 路由
│   │   ├── routes/               # 路由实现
│   │   │   ├── auth.py           # 认证
│   │   │   ├── chat.py           # 聊天
│   │   │   ├── session.py        # 会话管理
│   │   │   ├── skill.py          # Skills
│   │   │   ├── mcp.py            # MCP
│   │   │   ├── feedback.py      # 反馈
│   │   │   ├── upload.py         # 文件上传
│   │   │   └── share.py          # 分享
│   │   └── deps.py               # 依赖注入
│   ├── agents/                   # Agent 实现
│   │   ├── core/                 # 核心基类
│   │   └── search_agent/         # 搜索 Agent
│   ├── infra/                    # 基础设施
│   │   ├── agent/                # Agent 运行时
│   │   ├── auth/                 # 认证
│   │   ├── llm/                  # LLM 客户端
│   │   ├── tool/                 # 工具系统
│   │   ├── storage/              # 存储
│   │   ├── session/              # 会话管理
│   │   ├── feedback/             # 反馈系统
│   │   └── mcp/                  # MCP 集成
│   └── kernel/                   # 核心配置
├── frontend/                     # 前端源码
│   ├── src/
│   │   ├── components/           # UI 组件
│   │   │   ├── chat/             # 聊天组件
│   │   │   ├── documents/        # 文档预览
│   │   │   ├── auth/             # 认证组件
│   │   │   ├── panels/           # 侧边面板
│   │   │   └── mcp/              # MCP 管理
│   │   ├── hooks/                # React Hooks
│   │   ├── services/             # API 服务
│   │   ├── contexts/             # React Context
│   │   └── i18n/                 # 国际化
│   └── package.json
├── docs/                         # 文档
├── deploy/                       # 部署配置
├── docker-compose.yml            # Docker 编排
├── Makefile                      # 构建脚本
├── pyproject.toml                # Python 配置
└── README.md
```

## ⚙️ 配置说明

### 环境变量

| 变量 | 描述 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API Key | - |
| `LLM_MODEL` | 模型名称 | anthropic/claude-3-5-sonnet-20241022 |
| `MONGODB_URL` | MongoDB 连接串 | mongodb://localhost:27017 |
| `REDIS_URL` | Redis 连接串 | redis://localhost:6379 |
| `JWT_SECRET` | JWT 密钥 | - |
| `JWT_ALGORITHM` | JWT 算法 | HS256 |
| `JWT_EXPIRE_MINUTES` | Token 过期时间 | 1440 |

### 可选配置

| 变量 | 描述 |
|------|------|
| `LANGSMITH_API_KEY` | LangSmith 链路追踪 |
| `S3_ENDPOINT` | S3 兼容存储 endpoint |
| `S3_BUCKET` | S3 存储桶 |
| `OSS_ACCESS_KEY` | 阿里云 OSS |
| `GITHUB_TOKEN` | GitHub Skills 同步 |

## 🐳 Docker 部署

```bash
# 启动所有服务
make docker-up

# 查看日志
make docker-logs

# 停止服务
make docker-down

# 重启服务
make docker-restart
```

## 🛠️ 开发命令

```bash
# 安装依赖
make install              # 后端
make frontend-install     # 前端
make install-all          # 全部

# 开发运行
make dev                  # 后端
make frontend-dev         # 前端
make dev-all              # 全部

# 构建
make build
make frontend-build
make build-all

# 代码质量
make lint                 # 代码检查
make format               # 代码格式化
make test                 # 运行测试

# 清理
make clean                # 清理缓存
make clean-all            # 深度清理
```

## 🔧 技术栈

### 后端

| 技术 | 用途 |
|------|------|
| FastAPI | Web 框架 |
| LangGraph | Agent 编排 |
| LangChain | LLM 集成 |
| Redis | 实时存储 / 缓存 |
| MongoDB | 持久化存储 |
| SSE | 流式输出 |
| JWT | 认证 |

### 前端

| 技术 | 用途 |
|------|------|
| React 19 | UI 框架 |
| Vite | 构建工具 |
| TailwindCSS | 样式框架 |
| TypeScript | 类型安全 |
| react-markdown | Markdown 渲染 |
| mermaid | 图表渲染 |
| pdfjs-dist | PDF 预览 |
| xlsx | Excel 预览 |
| KaTeX | 数学公式 |

## 📄 License

MIT License - 查看 [LICENSE](LICENSE) 了解详情

---

<p align="center">Built with ❤️ using FastAPI + LangGraph + React</p>
