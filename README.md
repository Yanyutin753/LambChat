# LambChat

基于 FastAPI + LangGraph 构建的生产级 AI Agent 系统。

## 核心特性

### 🤖 LangGraph Agent 架构
- 每个 Agent 都是一个 **CompiledGraph**，支持流式输出
- 装饰器注册：`@register_agent("agent_id")`
- Agent 工厂单例模式管理

### 🎯 统一事件系统 (Presenter)
- 丰富的 SSE 事件：文本、思考过程、工具调用、子 Agent、代码块、文件操作、人工审批
- 支持主 Agent / 子 Agent 层级深度

### ⚡ 双写机制
- **Redis**: 实时写入，SSE 低延迟
- **MongoDB**: 批量缓冲，按 trace_id 聚合，确保数据不丢失
- 支持断线重连

### 🔌 MCP 集成
- 系统级 + 用户级 MCP 配置
- 敏感信息加密存储
- 动态缓存管理

### 🛠️ Skills 系统
- 文件系统 + MongoDB 双存储
- 用户级别技能访问控制
- GitHub 同步支持

### 🔐 权限与安全
- JWT 认证 + RBAC 角色（Admin/User/Guest）
- 多租户资源隔离

### 🎨 前端
- React + Vite + TailwindCSS
- ChatGPT 风格界面
- 多文档预览（PDF/Word/Excel/PPT/Markdown/Mermaid）
- 深色/浅色主题

## 快速开始

```bash
# 安装依赖
make install

# 配置环境变量 (.env)
LLM_API_KEY=your_key
LLM_MODEL=anthropic/claude-3-5-sonnet-20241022

# 启动服务
make dev-all
```

- API 文档: <http://localhost:8000/docs>
- 前端: <http://localhost:5173>

## 核心 API

```bash
# 认证
POST /api/auth/register
POST /api/auth/login

# 聊天 (SSE 流式)
POST /api/chat/stream
GET /api/chat/sessions/{session_id}/stream

# Skills
GET /api/skills
POST /api/skills/sync-github

# MCP
GET /api/mcp/servers
POST /api/mcp/servers
```

## 技术栈

- **后端**: FastAPI, LangGraph, LangChain, Redis, MongoDB
- **前端**: React, Vite, TailwindCSS, TypeScript

## License

MIT
