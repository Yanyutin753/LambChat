<div align="center">

# 🐑 LambChat

**基于 FastAPI + deepagents 构建的生产级 AI Agent 系统**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)]()
[![React](https://img.shields.io/badge/React-19-green.svg)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-orange.svg)]()
[![deepagents](https://img.shields.io/badge/deepagents-Latest-purple.svg)]()
[![MongoDB](https://img.shields.io/badge/MongoDB-Latest-green.svg)]()
[![Redis](https://img.shields.io/badge/Redis-Latest-red.svg)]()
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) · [简体中文](README_CN.md) · [参与贡献](CONTRIBUTING.md)

</div>

---

## 📸 界面展示

| | | |
|:---:|:---:|:---:|
| <img src="docs/images/best-practice/login-page.png" width="280" alt="登录"><br>**登录** | <img src="docs/images/best-practice/chat-home.png" width="280" alt="聊天"><br>**聊天** | <img src="docs/images/best-practice/chat-response.png" width="280" alt="流式"><br>**流式输出** |
| <img src="docs/images/best-practice/skills-page.png" width="280" alt="技能"><br>**技能** | <img src="docs/images/best-practice/mcp-page.png" width="280" alt="MCP"><br>**MCP 配置** | <img src="docs/images/best-practice/share-dialog.png" width="280" alt="分享"><br>**分享** |
| <img src="docs/images/best-practice/roles-page.png" width="280" alt="角色"><br>**角色管理** | <img src="docs/images/best-practice/settings-page.png" width="280" alt="设置"><br>**系统设置** | <img src="docs/images/best-practice/mobile-view.png" width="200" alt="移动端"><br>**移动端** |

## 🏗️ 系统架构

<p align="center"><img src="docs/images/best-practice/architecture.png" width="600" alt="架构"></p>

## ✨ 核心特性

<details>
<summary><b>🤖 Agent 系统</b></summary>

- **deepagents 架构** — 编译图架构，细粒度状态管理
- **多 Agent 类型** — 核心 / 快速 / 搜索 Agent
- **插件系统** — `@register_agent("id")` 装饰器注册自定义 Agent
- **流式输出** — 原生 SSE 支持
- **子 Agent** — 多层级嵌套
- **思考模式** — 支持 Anthropic 扩展思考
- **人工审批** — 敏感操作审批流程

</details>

<details>
<summary><b>🔌 MCP 集成</b></summary>

- **系统级 + 用户级** — 全局和个人 MCP 配置
- **加密存储** — API Key 加密存储
- **动态缓存** — 工具缓存，支持手动刷新
- **多种传输** — SSE / HTTP
- **权限控制** — 传输协议级别访问控制

</details>

<details>
<summary><b>🛠️ 技能系统</b></summary>

- **双存储** — 文件系统 + MongoDB 备份
- **访问控制** — 用户级别权限
- **GitHub 同步** — 从 GitHub 同步自定义技能
- **技能创建** — 内置创建工具包，含评估和基准测试

</details>

<details>
<summary><b>💬 反馈 · 📁 文件 · 🔄 实时 · 🔐 认证 · ⚙️ 任务 · 📊 可观测性</b></summary>

- **反馈** — 点赞评分、文字评论、会话关联、运行级别统计
- **文档** — PDF / Word / Excel / PPT / Markdown / Mermaid 预览 + 图片查看器
- **云存储** — S3 / OSS / MinIO 集成，拖拽上传
- **实时** — 双写机制（Redis + MongoDB）、WebSocket、自动重连、会话分享
- **安全** — JWT、RBAC（Admin/User/Guest）、bcrypt、OAuth、邮箱验证、沙箱
- **任务** — 并发控制、任务取消、心跳监控、发布/订阅通知
- **可观测性** — LangSmith 链路追踪、结构化日志、健康检查
- **渠道** — 飞书原生集成，可扩展多渠道系统

</details>

<details>
<summary><b>🎨 前端</b></summary>

- **React 19 + Vite + TailwindCSS**
- **ChatGPT 风格** 界面，深色/浅色主题切换
- **国际化** — 英文、中文、日文、韩文
- **响应式** — 移动端、平板、桌面端适配

</details>

## ⚙️ 配置说明

支持 14 个设置分类，可通过 UI 或环境变量配置：

| 分类 | 说明 |
|------|------|
| 前端 | 默认 Agent、欢迎建议、UI 偏好 |
| Agent | 调试模式、日志级别 |
| LLM | 模型、温度、最大 Token、API 密钥和基础 URL |
| 会话 | 会话管理 |
| 数据库 | MongoDB 连接 |
| 存储 | 持久化存储、S3/OSS/MinIO |
| 安全 | 加密与安全策略 |
| 沙箱 | 代码沙箱设置 |
| 技能 | 技能系统配置 |
| 工具 | 工具系统设置 |
| 追踪 | LangSmith 链路追踪 |
| 用户 | 用户管理 |
| 记忆 | 记忆系统（hindsight） |

## 🚀 快速开始

### 环境要求

- Python 3.12+ · Node.js 18+ · MongoDB · Redis

### 安装

```bash
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# Docker 启动（推荐）
cd deploy && cp .env.example .env   # 编辑填写配置
docker compose up -d

# 或本地运行
cp .env.example .env   # 编辑填写配置
make install && make dev
```

→ 打开 **http://localhost:8000**

### 代码质量

```bash
ruff format src/    # 格式化
ruff check src/     # 检查风格
mypy src/           # 类型检查
```

### 项目结构

```
src/
├── agents/          # Agent 实现（核心、快速、搜索）
├── api/             # FastAPI 路由与中间件
├── infra/           # 基础设施服务
│   ├── agent/       # Agent 配置与事件
│   ├── auth/        # JWT 认证
│   ├── channel/     # 多渠道（飞书等）
│   ├── feedback/    # 反馈系统
│   ├── llm/         # LLM 集成
│   ├── mcp/         # MCP 协议
│   ├── memory/      # 记忆与 hindsight
│   ├── role/        # RBAC 角色
│   ├── sandbox/     # 沙箱执行
│   ├── session/     # 会话管理（双写）
│   ├── skill/       # 技能系统
│   ├── storage/     # S3/OSS/MinIO
│   ├── task/        # 任务管理
│   ├── tool/        # 工具注册与 MCP 客户端
│   └── ...
├── kernel/          # 核心模型、配置、类型
└── skills/          # 内置技能
```

## ⭐ Star History

<a href="https://star-history.com/#Yanyutin753/LambChat&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date" />
 </picture>
</a>

## 📄 许可证

[MIT](LICENSE) — 项目名称 "LambChat" 及其标志不得被更改或移除。

---

<div align="center">

Made with ❤️ by [Clivia](https://github.com/Yanyutin753)

[📧 3254822118@qq.com](mailto:3254822118@qq.com) · [GitHub](https://github.com/Yanyutin753)

</div>
