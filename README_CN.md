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
| <img src="docs/images/best-practice/login-page.webp" width="280" alt="登录"><br>**登录** | <img src="docs/images/best-practice/chat-home.webp" width="280" alt="聊天"><br>**聊天** | <img src="docs/images/best-practice/chat-response.webp" width="280" alt="流式"><br>**流式输出** |
| <img src="docs/images/best-practice/skills-page.webp" width="280" alt="技能"><br>**技能** | <img src="docs/images/best-practice/mcp-page.webp" width="280" alt="MCP"><br>**MCP 配置** | <img src="docs/images/best-practice/share-dialog.webp" width="280" alt="分享"><br>**分享** |
| <img src="docs/images/best-practice/roles-page.webp" width="280" alt="角色"><br>**角色管理** | <img src="docs/images/best-practice/settings-page.webp" width="280" alt="设置"><br>**系统设置** | <img src="docs/images/best-practice/feedback-page.webp" width="280" alt="反馈"><br>**反馈** |
| <img src="docs/images/best-practice/mobile-view.webp" width="200" alt="移动端"><br>**移动端** | <img src="docs/images/best-practice/tablet-view.webp" width="280" alt="平板"><br>**平板端** | <img src="docs/images/best-practice/shared-page.webp" width="280" alt="分享页"><br>**会话分享** |

## 🎬 实战案例

| # | 案例 | 说明 | 演示 |
|---|------|------|------|
| 1 | PDF 商业报告生成 | Agent 自动读取 Skill 说明 → 安装依赖 → 生成 8 张专业图表 → 编写 LaTeX 源码 → 编译为 14 页 PDF 商业报告，全程零人工干预。 | [查看会话](https://lambchat.com/shared/Yaotot5Fav8j) |
| 2 | PPT 商业演示文稿 | 基于供应链数据，Agent 独立完成 14 页商务 PPT，包含数据表格、图表、分析卡片和行动路线图。 | [查看会话](https://lambchat.com/shared/VOjediSYBHR1) |
| 3 | 静态博客网站搭建 | 从零搭建完整个人博客（5 个页面 + 8 篇示例文章），包含标签筛选、分页、响应式布局和交互效果，10 个子任务全部自动完成。 | [查看会话](https://lambchat.com/shared/NuzvONPqCZLU) |

## 🏗️ 系统架构

<p align="center"><img src="docs/images/best-practice/architecture.webp" width="600" alt="架构"></p>

## ✨ 核心特性

<details>
<summary><b>🤖 Agent 系统</b></summary>

- **deepagents 架构** — 编译图架构，细粒度状态管理
- **多 Agent 类型** — 核心 / 快速 / 搜索 Agent
- **插件系统** — `@register_agent("id")` 装饰器注册自定义 Agent
- **流式输出** — 原生 SSE 支持
- **子 Agent** — 多层级嵌套
- **思考模式** — 支持 Anthropic 扩展思考
- **人工审批** — 带倒计时、自动延期和紧急状态样式的审批系统

</details>

<details>
<summary><b>🧠 模型管理</b></summary>

- **多供应商** — OpenAI、Anthropic、Google Gemini、Kimi（月之暗面）
- **完整 CRUD** — 通过 UI 创建、编辑、删除、批量导入模型，支持每模型独立配置（api_key、api_base、temperature、max_tokens）
- **渠道路由** — 同一模型通过 `model_id` 路由支持多个渠道
- **角色权限** — `MODEL_ADMIN` 权限，按角色控制模型可见性
- **用户偏好** — 默认模型选择跨会话持久化
- **实时同步** — Redis 分布式发布/订阅实时更新模型配置
- **拖拽排序** — 模型选择器中拖拽重排模型顺序

</details>

<details>
<summary><b>🔌 MCP 集成</b></summary>

- **系统级 + 用户级** — 全局和个人 MCP 配置
- **加密存储** — API Key 加密存储
- **动态缓存** — 工具缓存，支持手动刷新
- **多种传输** — SSE / HTTP
- **权限控制** — 传输协议级别访问控制
- **导入导出** — 批量 MCP 配置管理

</details>

<details>
<summary><b>🛠️ 技能系统</b></summary>

- **双存储** — 文件系统 + MongoDB 备份
- **访问控制** — 用户级别权限
- **GitHub 同步** — 从 GitHub 同步自定义技能
- **技能创建** — 内置创建工具包，含评估和基准测试
- **技能市场** — 浏览、安装和发布技能
- **批量操作** — 批量启用/禁用/删除技能

</details>

<details>
<summary><b>💬 反馈 · 📁 文件 · 🔄 实时 · 🔐 认证 · ⚙️ 任务 · 📊 可观测性</b></summary>

- **反馈** — 点赞评分、文字评论、会话关联、运行级别统计
- **文件库** — 浏览已揭示文件、代码预览，支持网格/列表视图、收藏、项目级筛选
- **文档** — PDF / Word / Excel / PPT / Markdown / Mermaid / Excalidraw 预览 + 图片查看器
- **云存储** — S3 / OSS / MinIO / COS 集成，拖拽上传，预签名 URL
- **项目文件夹** — 拖拽方式将会话组织到项目中
- **会话分享** — 生成公开分享链接
- **实时** — 双写机制（Redis + MongoDB）、WebSocket、自动重连、会话分享
- **安全** — JWT、RBAC（15 组 35+ 细粒度权限）、bcrypt、OAuth（Google/GitHub/Apple）、邮箱验证、验证码、沙箱
- **任务** — 并发控制、任务取消、心跳监控、发布/订阅通知
- **可观测性** — LangSmith 链路追踪、结构化日志、健康检查
- **渠道** — 飞书原生集成，支持模型选择器、项目绑定、基于时间的会话标题，可扩展多渠道系统

</details>

<details>
<summary><b>🎨 前端</b></summary>

- **React 19 + Vite 6 + TailwindCSS 3.4**
- **ChatGPT 风格** 界面，深色/浅色主题切换
- **毛玻璃设计系统** — 全局统一的 glass-shell/glass-card 风格
- **国际化** — 英文、中文、日文、韩文、俄文
- **响应式** — 移动端、平板、桌面端统一组件渲染
- **富内容** — KaTeX 数学公式、代码高亮、Mermaid 图表、表格复制/CSV 导出、图片预览灯箱、行高亮代码查看器
- **工具面板** — 滑出式工具结果面板，支持居中/侧边视图模式和块预览门户
- **骨架屏加载** — 骨架屏组件提升感知性能
- **Landing 页面** — 高级博客风格首页，滚动动画和区域追踪

</details>

## ⚙️ 配置说明

支持 14+ 个设置分类，可通过 UI 或环境变量配置：

| 分类 | 说明 |
|------|------|
| 前端 | 默认 Agent、欢迎建议、UI 偏好 |
| Agent | 调试模式、日志级别 |
| 模型 | 多供应商模型管理、每模型独立配置、渠道路由 |
| 会话 | 会话管理、消息历史、SSE 缓存 |
| 数据库 | MongoDB 连接，可选 PostgreSQL |
| 存储 | 持久化存储、S3/OSS/MinIO/COS |
| 安全 | 加密与安全策略 |
| 沙箱 | 代码沙箱设置（Daytona / E2B） |
| 技能 | 技能系统配置 |
| 工具 | 工具系统设置 |
| 追踪 | LangSmith 链路追踪 |
| 用户 | 用户管理、注册、默认角色 |
| 记忆 | 记忆系统（native / hindsight / memu） |

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
│   ├── routes/      # 27 路由模块（auth、chat、mcp、skills、model 等）
│   ├── admin/       # 管理 API 端点
│   └── agent/       # Agent 配置与模型管理
├── infra/           # 基础设施服务
│   ├── agent/       # Agent 配置与事件
│   ├── auth/        # JWT、OAuth、RBAC、验证码
│   ├── backend/     # LLM 后端抽象
│   ├── channel/     # 多渠道（飞书等）
│   ├── email/       # 邮件服务（Resend）
│   ├── envvar/      # 用户环境变量
│   ├── feedback/    # 反馈系统
│   ├── folder/      # 项目文件夹管理
│   ├── llm/         # LLM 集成（OpenAI、Anthropic、Gemini、Kimi）
│   ├── memory/      # 跨会话记忆（native、hindsight、memu）
│   ├── model/       # 模型管理（加密存储、发布/订阅同步）
│   ├── mcp/         # MCP 协议
│   ├── role/        # RBAC 角色
│   ├── sandbox/     # 沙箱执行（Daytona / E2B）
│   ├── session/     # 会话管理（双写）
│   ├── settings/    # 设置存储 + 发布/订阅同步
│   ├── share/       # 分享链接
│   ├── skill/       # 技能系统
│   ├── storage/     # MongoDB、Redis、PostgreSQL、S3
│   ├── task/        # 任务管理
│   ├── tool/        # 工具注册与 MCP 客户端
│   ├── tracing/     # LangSmith 链路追踪
│   ├── upload/      # 文件上传处理
│   ├── revealed_file/  # 文件库
│   └── websocket/   # WebSocket 与限流
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
