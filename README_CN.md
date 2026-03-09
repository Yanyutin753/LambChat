# LambChat

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/React-19-green.svg" alt="React">
  <img src="https://img.shields.io/badge/FastAPI-Latest-orange.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/LangGraph-Latest-purple.svg" alt="LangGraph">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
</p>

[English](README.md) | 简体中文

> 基于 FastAPI + LangGraph 构建的生产级 AI Agent 系统

## ✨ 核心特性

### 🤖 Agent 系统
- **LangGraph 架构** - 编译图架构，支持细粒度状态管理
- **插件系统** - 使用 `@register_agent("id")` 装饰器快速注册自定义 Agent
- **流式输出** - 原生支持 SSE (Server-Sent Events)
- **子 Agent** - 支持多层级 Agent 嵌套

### 🔌 MCP 集成
- **系统级 + 用户级 MCP** - 支持全局和个人 MCP 服务器配置
- **加密存储** - API Keys 等敏感信息加密存储
- **动态缓存** - 工具缓存管理，支持手动刷新

### 🛠️ Skills 系统
- **双存储** - 文件系统 + MongoDB 双存储备份
- **访问控制** - 用户级别技能访问控制
- **GitHub 同步** - 支持从 GitHub 同步自定义 Skills

### 💬 反馈系统
- **点赞评分** - 简单的赞成/反对反馈
- **文字评论** - 详细的用户反馈
- **会话关联** - 反馈与具体会话/消息关联

### 🔐 安全
- **JWT 认证** - 完整的认证流程
- **RBAC 角色** - Admin / User / Guest 三级角色
- **多租户** - 租户级别的资源隔离
- **密码加密** - bcrypt 哈希加密

### 🎨 前端
- **现代技术栈** - React 19 + Vite + TailwindCSS
- **ChatGPT 风格** - 熟悉的对话界面体验
- **文档预览** - PDF / Word / Excel / PPT / Markdown / Mermaid
- **主题切换** - 深色/浅色模式
- **国际化** - 多语言支持

### ⚡ 实时 & 存储
- **双写机制** - Redis 实时写入，MongoDB 持久化存储
- **自动重连** - 断线后自动恢复对话
- **S3/OSS 支持** - 云存储集成

## 🚀 快速开始

```bash
# 克隆仓库
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# 复制环境变量文件
cp .env.example .env

# Docker 启动
docker-compose up -d

# 或本地运行
make install  # 安装依赖
make dev      # 启动开发服务器
```

访问 `http://localhost:8000`

## 📄 许可证

[MIT](LICENSE)

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/Yanyutin753">Clivia</a>
</p>
