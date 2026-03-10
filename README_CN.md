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

## 📸 界面展示

### 主要界面

<table>
  <tr>
    <td align="center"><b>登录页面</b></td>
    <td align="center"><b>聊天界面</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/login-page.png" alt="登录页面" width="400"/></td>
    <td><img src="docs/images/best-practice/chat-home.png" alt="聊天界面" width="400"/></td>
  </tr>
  <tr>
    <td align="center"><b>流式输出</b></td>
    <td align="center"><b>分享对话框</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/chat-response.png" alt="流式输出" width="400"/></td>
    <td><img src="docs/images/best-practice/share-dialog.png" alt="分享对话框" width="400"/></td>
  </tr>
</table>

### 管理面板

<table>
  <tr>
    <td align="center"><b>技能管理</b></td>
    <td align="center"><b>MCP 配置</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/skills-page.png" alt="技能管理" width="400"/></td>
    <td><img src="docs/images/best-practice/mcp-page.png" alt="MCP 配置" width="400"/></td>
  </tr>
  <tr>
    <td align="center"><b>系统设置</b></td>
    <td align="center"><b>反馈系统</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/settings-page.png" alt="系统设置" width="400"/></td>
    <td><img src="docs/images/best-practice/feedback-page.png" alt="反馈系统" width="400"/></td>
  </tr>
  <tr>
    <td align="center"><b>分享会话</b></td>
    <td align="center"><b>角色管理</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/shared-page.png" alt="分享会话" width="400"/></td>
    <td><img src="docs/images/best-practice/roles-page.png" alt="角色管理" width="400"/></td>
  </tr>
</table>

### 响应式设计

<table>
  <tr>
    <td align="center"><b>移动端视图</b></td>
    <td align="center"><b>平板视图</b></td>
  </tr>
  <tr>
    <td><img src="docs/images/best-practice/mobile-view.png" alt="移动端视图" width="250"/></td>
    <td><img src="docs/images/best-practice/tablet-view.png" alt="平板视图" width="350"/></td>
  </tr>
</table>

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
