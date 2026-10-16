<div align="center">

# 🐑 LambChat

**运行在云端的个人 AI Agent —— 开源、自托管、全天候在线，需要时也是多租户平台。**

[![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-19-green.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Latest-orange.svg)](https://fastapi.tiangolo.com/)
[![deepagents](https://img.shields.io/badge/deepagents-Latest-purple.svg)](https://github.com/langchain-ai/deepagents)
[![MongoDB](https://img.shields.io/badge/MongoDB-Latest-green.svg)](https://www.mongodb.com/)
[![Redis](https://img.shields.io/badge/Redis-Latest-red.svg)](https://redis.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](README.md) · [简体中文](README_CN.md) · [文档](https://yanyutin753.github.io/LambChat/zh/) · [参与贡献](CONTRIBUTING.md)

<br>

<img src="docs/images/readme/hero.webp" alt="LambChat 个人 AI Agent" width="920">

</div>

---

## 认识你的 Agent

大多数 AI 产品只是一段对话，关掉标签页就结束了。LambChat 是一个**部署一次、常驻你自己云端的个人 Agent**。它一直在线：跨会话记得你的上下文，运行你选的模型，调用你的 MCP 工具，在隔离沙箱里执行真正的工作，并把成品——报告、网站、分析、图集——送到你的每一台设备，或直接推进你的 IM。你不在的时候，定时任务照常运行，干完活再来通知你。

因为是自托管，你的密钥、记忆和文件始终属于你自己。

## 单人使用与多租户

同一套部署，两种用法：

| 只有你 | 一整个团队 |
|---|---|
| <img src="docs/images/illustrations/lamb-avatar.webp" width="64" alt="单人私享"><br>**你自己** | <img src="docs/images/illustrations/lamb-panel-team.webp" width="64" alt="团队平台"><br>**你的团队** |
| 一个账号，你的记忆、技能和密钥——Agent 只为你工作、一直记得你。 | 多用户账号体系，支持注册审批、OAuth 登录和 RBAC 角色。 |
| 定时任务与 IM 渠道让它全天候运转、随时可达。 | 按角色的模型可见性、用户默认模型、会话分享、反馈和用量统计。 |
| 每份交付物都落进文件库，留存可查。 | 管理员**批量创建模型**、统一管理 MCP 服务器——其他人开箱即用。 |

## 凭什么是「个人 Agent」

| 它记得你 | 它用你的工具 | 它干真正的活 | 它随时找到你 |
|---|---|---|---|
| <img src="docs/images/illustrations/lamb-reading.webp" width="96" alt="小羊在阅读"><br>**记得你** | <img src="docs/images/illustrations/lamb-welcome.webp" width="96" alt="小羊与你的工具"><br>**你的工具** | <img src="docs/images/illustrations/lamb-files.webp" width="96" alt="小羊在干活"><br>**真干活** | <img src="docs/images/illustrations/lamb-message.webp" width="96" alt="小羊来找你"><br>**找到你** |
| 跨会话记忆、人格预设、越用越多的技能沉淀——明天它还认识你，而不只记得这一场对话。 | 多供应商模型、系统级/用户级 MCP（密钥加密存储）、丰富网页搜索——一切都自带。 | deepagents/LangGraph 运行时，子 Agent 委派、人工审批、沙箱代码执行，产出真实交付物。 | Web、PWA、移动端、桌面端实时同步，外加飞书/Lark、微信、Telegram、Slack、钉钉、Discord、邮件等 15+ 通知渠道。 |

| 你想要... | 推荐入口 |
|---|---|
| 先看看 Agent 能做什么 | [产品预览](#产品预览) 和 [实战案例](#实战案例) |
| 单人用还是给团队用 | [单人使用与多租户](#单人使用与多租户) |
| 快速跑起来 | [快速开始](#快速开始) |
| 理解系统结构 | [系统架构](#系统架构) 和 [工作原理](#工作原理) |
| 配置生产环境 | [配置说明](#配置说明) 和 [部署文档](https://yanyutin753.github.io/LambChat/zh/deploy/docker.html) |
| 参与开发 | [开发指南](#开发指南) 和 [贡献指南](CONTRIBUTING.md) |

## 产品预览

更新于 2026 年 10 月 16 日。截图来自当前界面组件，使用演示数据；浅色与深色版本随设备配色切换。

| 对话与执行 | 技能市场 | 模型管理 |
|:---:|:---:|:---:|
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/chat-response-dark.webp" /><img src="docs/images/best-practice/chat-response.webp" width="300" alt="流式 Agent 响应"></picture><br>**流式 Agent 工作** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/marketplace-page-dark.webp" /><img src="docs/images/best-practice/marketplace-page.webp" width="300" alt="技能市场"></picture><br>**越积越多的技能** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/models-page-dark.webp" /><img src="docs/images/best-practice/models-page.webp" width="300" alt="模型配置"></picture><br>**你的模型你的密钥** |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/files-page-dark.webp" /><img src="docs/images/best-practice/files-page.webp" width="300" alt="文件库"></picture><br>**交付物文件库** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/mcp-page-dark.webp" /><img src="docs/images/best-practice/mcp-page.webp" width="300" alt="MCP 配置"></picture><br>**MCP 工具** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/mobile-view-dark.webp" /><img src="docs/images/best-practice/mobile-view.webp" width="92" height="200" alt="移动端响应式视图"></picture><br>**处处都在** |

<details>
<summary><b>查看完整界面图库</b></summary>

| | | |
|:---:|:---:|:---:|
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/login-page-dark.webp" /><img src="docs/images/best-practice/login-page.webp" width="280" alt="登录"></picture><br>**登录** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/register-page-dark.webp" /><img src="docs/images/best-practice/register-page.webp" width="280" alt="注册"></picture><br>**注册** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/reset-request-page-dark.webp" /><img src="docs/images/best-practice/reset-request-page.webp" width="280" alt="重置密码"></picture><br>**重置密码** |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/verify-email-page-dark.webp" /><img src="docs/images/best-practice/verify-email-page.webp" width="280" alt="邮箱验证"></picture><br>**邮箱验证** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/registration-pending-page-dark.webp" /><img src="docs/images/best-practice/registration-pending-page.webp" width="280" alt="注册待审核"></picture><br>**注册待审核** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/chat-home-dark.webp" /><img src="docs/images/best-practice/chat-home.webp" width="280" alt="聊天"></picture><br>**聊天** |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/chat-response-dark.webp" /><img src="docs/images/best-practice/chat-response.webp" width="280" alt="流式"></picture><br>**流式输出** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/share-dialog-dark.webp" /><img src="docs/images/best-practice/share-dialog.webp" width="280" alt="分享"></picture><br>**分享** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/skills-page-dark.webp" /><img src="docs/images/best-practice/skills-page.webp" width="280" alt="技能"></picture><br>**技能** |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/marketplace-page-dark.webp" /><img src="docs/images/best-practice/marketplace-page.webp" width="280" alt="技能市场"></picture><br>**技能市场** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/mcp-page-dark.webp" /><img src="docs/images/best-practice/mcp-page.webp" width="280" alt="MCP"></picture><br>**MCP 配置** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/agents-page-dark.webp" /><img src="docs/images/best-practice/agents-page.webp" width="280" alt="智能体"></picture><br>**智能体** |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/models-page-dark.webp" /><img src="docs/images/best-practice/models-page.webp" width="280" alt="模型"></picture><br>**模型** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/channels-page-dark.webp" /><img src="docs/images/best-practice/channels-page.webp" width="280" alt="渠道"></picture><br>**渠道** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/files-page-dark.webp" /><img src="docs/images/best-practice/files-page.webp" width="280" alt="文件"></picture><br>**文件** |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/persona-page-dark.webp" /><img src="docs/images/best-practice/persona-page.webp" width="280" alt="角色广场"></picture><br>**角色广场** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/memory-page-dark.webp" /><img src="docs/images/best-practice/memory-page.webp" width="280" alt="记忆"></picture><br>**记忆** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/notifications-page-dark.webp" /><img src="docs/images/best-practice/notifications-page.webp" width="280" alt="通知"></picture><br>**通知** |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/settings-page-dark.webp" /><img src="docs/images/best-practice/settings-page.webp" width="280" alt="设置"></picture><br>**系统设置** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/feedback-page-dark.webp" /><img src="docs/images/best-practice/feedback-page.webp" width="280" alt="反馈"></picture><br>**反馈** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/shared-page-dark.webp" /><img src="docs/images/best-practice/shared-page.webp" width="280" alt="分享页"></picture><br>**会话分享** |
| <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/roles-page-dark.webp" /><img src="docs/images/best-practice/roles-page.webp" width="280" alt="角色"></picture><br>**角色管理** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/users-page-dark.webp" /><img src="docs/images/best-practice/users-page.webp" width="280" alt="用户"></picture><br>**用户管理** | <picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/tablet-view-dark.webp" /><img src="docs/images/best-practice/tablet-view.webp" width="148" height="190" alt="平板"></picture><br>**平板端** |

</details>

## 实战案例

这些公开会话展示了你的 Agent 能承接的端到端工作——每一个都以真实交付物收尾，而不是一段聊天记录。

| # | 案例 | Agent 做了什么 | 演示 |
|---|---|---|---|
| 1 | 供应链效率分析 PDF 报告 | 从一句需求出发，自动生成图表、基准对比和完整交付物，输出可直接使用的供应链效率分析 PDF 报告。 | [查看会话](https://lambchat.com/shared/w0WA7GtMCyca) |
| 2 | 教父三部曲主题英文网站 | 自动搭建面向影迷的英文专题网页，包含电影感视觉风格、跑马灯 Hero、生成图片和多端适配。 | [查看会话](https://lambchat.com/shared/9XlmaDANCjO9) |
| 3 | 图片内容故事全解 | 基于图片进行多模态理解，识别其中包含的故事，并输出逐个展开的详细剧情讲解。 | [查看会话](https://lambchat.com/shared/MZX-eNnOoilN) |
| 4 | 新能源汽车市场趋势分析 | 基于 2025-2026 最新数据整理结构化市场洞察，覆盖增长趋势、区域表现和行业关键信号。 | [查看会话](https://lambchat.com/shared/5XUeuDEyd2CY) |
| 5 | 批量生成游戏 UI 素材 | 输入一张参考图，Agent 自动分析美术风格，生成 **48 个游戏 UI Icon**，按 9 个类别分文件夹整理，并把流程保存成可复用技能。 | [查看会话](https://lambchat.com/shared/IsLxtk1RJ7wn) |
| 6 | 电商商品全自动组图 | 输入商品关键词和目标平台，Agent 自动完成人群分析、视觉策略、主图、生活场景图、细节图和搭配图生成。 | [查看会话](https://lambchat.com/shared/wgs2zatzGi_2) |
| 7 | 多 Agent 协作电商设计 | **4 个 Agent 协作**（创意总监、设计师、AI 图像工程师、审核师）在一个会话内完成品牌电商组图的全流程：创意策略、设计生成、审核反馈、修改交付。 | [查看会话](https://lambchat.com/shared/e6OCDGkrpgU1) |
| 8 | 每日 AI 前沿论文推送（定时任务） | 一个**定时任务**每天自动运行——没人在键盘前——搜索 arXiv 5 个方向（VLA、世界模型、LLM 推理、多模态、Agent）的最新论文，筛选整理后生成结构化趋势总结。 | [查看会话](https://lambchat.com/shared/G-uQf_O-wXnQ) |

## 工作原理

<details open>
<summary><b>能把活干完的运行时</b></summary>

- **deepagents 架构**：编译图运行时，支持细粒度状态管理。
- **三类内置 Agent**：`quick` 负责日常问答、写作与翻译；`search` 负责研究、工具调用与沙箱执行；`team` 负责角色搜索、子代理分派与持续协作。
- **插件注册**：通过 `@register_agent("id")` 接入自定义 Agent。
- **流式输出**：原生 SSE——实时看着 Agent 思考、调工具、写内容。
- **子 Agent**：支持多层级任务委派。
- **思考模式**：支持扩展推理。
- **人工审批**：Agent 需要你签字时，带倒计时和自动延期。
- **`/goal` 命令** — 通过 `/goal <目标>` 为任意 Run 附带评分标准引导的目标，支持自定义评分标准（`/goal <目标> --- <评分标准>`），SSE 事件追踪，完成后自动消失。

</details>

<details open>
<summary><b>它记得你</b></summary>

- **跨会话记忆**：MongoDB 原生存储——偏好、项目、经验教训跨对话跨设备留存。
- **人格预设**：可复用配置、权限控制和运行时绑定。
- **技能沉淀**：把一套流程封装一次（比如上面那个 48 图标批量生成），Agent 以后永远复用——双存储、访问控制、GitHub 同步、市场发布和创建工具一应俱全。

</details>

<details open>
<summary><b>你的模型你的密钥</b></summary>

- **多供应商模型**：OpenAI、Anthropic、Google Gemini、Kimi 等——UI 里配置、加密存储，不用在 `.env` 里倒腾密钥。
- **模型 CRUD 与批量创建**：一次批量创建多个模型，再统一编辑、排序或删除。
- **渠道路由**：同一模型经不同渠道复用（`model_id`）。
- **Fallback 模型**：供应商挂了，任务还能活下去。
- **角色级模型可见性**：`MODEL_ADMIN` 与按角色授权——管理员批量建好模型，每个角色只看到该看的。

</details>

<details open>
<summary><b>工具、MCP 与沙箱执行</b></summary>

- **系统级/用户级 MCP 服务器**：接入你已在用的工具，密钥静态加密、动态工具缓存、SSE/HTTP 传输、导入导出和工具级访问控制。
- **丰富网页搜索**：域名过滤、时间范围、地区优化及内容大小控制。
- **沙箱执行**：Daytona、E2B 或 CubeSandbox——桌面端还可用本地沙箱 daemon——Agent 能安全地写代码、跑代码。
- **内置工具**：文件揭示、项目揭示、上传 URL、环境变量、音频转写、人格预设等。

</details>

<details open>
<summary><b>常驻在线，随时可达</b></summary>

- **定时任务**：cron、interval、date 和手动触发，调度状态持久化，配合并发控制、任务取消和心跳监控——你睡着的时候 Agent 在干活。
- **通知渠道**：飞书/Lark、微信、企业微信、Telegram、Slack、钉钉、Discord、Bark、Pushover、ntfy、Gotify、邮件和通用 webhook——结果送到你已经在的地方。
- **实时同步**：Redis + MongoDB 双写、WebSocket 更新、自动重连和会话分享更新——任务跑到一半换台设备接着看。
- **全端客户端**：React 19 Web（PWA）、Capacitor Android/iOS 应用和 Tauri 桌面端，五种语言、深浅色主题。

</details>

<details open>
<summary><b>交付物，不是聊天气泡</b></summary>

- **文件库**：揭示文件、代码预览、收藏和项目筛选——Agent 产出的每样东西都留存可查。
- **富预览**：PDF、Word、Excel、PPT、Markdown、Mermaid、Excalidraw、图片和视频。
- **项目文件夹**：拖拽整理会话。
- **会话分享**：公开链接分享整段对话。
- **反馈闭环**：点赞/踩、文字评论、会话关联反馈和运行级统计。

</details>

<details open>
<summary><b>默认安全</b></summary>

- **安全**：JWT、RBAC、bcrypt、OAuth、邮箱验证、验证码和沙箱执行边界。
- **可观测**：LangSmith 链路追踪、结构化日志、健康检查和分布式记忆诊断。
- **任务运行时**：本地执行或 Redis arq 队列。

</details>

## 系统架构

<p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="docs/images/best-practice/architecture-dark.webp" /><img src="docs/images/best-practice/architecture.webp" width="1000" alt="LambChat 系统架构"></picture></p>

一套自托管控制平面：FastAPI 后端承载 LangGraph/deepagents 执行、Redis/MongoDB 持久化和沙箱隔离，前面是 React 19 工作台。

- **前端**：React 19、Vite、TailwindCSS、PWA workers、Capacitor 移动端构建和 Tauri 桌面端打包。
- **后端**：FastAPI、SSE/WebSocket 流式通信、鉴权/RBAC、调度器、存储服务、模型路由和 MCP 管理。
- **Agent 运行时**：deepagents/LangGraph 执行、子 Agent、人工审批、技能、记忆、工具和沙箱集成。
- **持久化与队列**：MongoDB、Redis、可选 PostgreSQL checkpoint、S3 兼容对象存储和 arq worker。

| | | |
|:---:|:---:|:---:|
| **14+** 设置类别 | **3** 种 Agent 类型 | **5** 种语言 |
| **3+** OAuth 提供商 | **SSE** 流式输出 | **15+** 通知渠道 |

## 快速开始

### 前置要求

- Python `>=3.12, <3.15`
- [uv](https://docs.astral.sh/uv/)（Python 包管理器）
- Node.js 22.22.2+
- [pnpm](https://pnpm.io/) 10+
- MongoDB
- Redis

### Docker（推荐）

```bash
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

cd deploy
cp .env.example .env
docker compose up -d
```

打开 **http://localhost:8000**。

### 本地开发

安装依赖：

```bash
cp .env.example .env
make install-all
```

同时启动前后端：

```bash
make dev-all
```

后端：**http://127.0.0.1:8000**
前端开发服务器：**http://127.0.0.1:3001**

也可以分开运行：

```bash
make dev            # FastAPI 后端：uv run python main.py
make frontend-dev   # Vite 前端
```

> LLM 模型部署后在 **Model Config UI** 里配置，基础启动路径无需在环境变量里放模型密钥。

接上你的模型、MCP 服务器、技能和 IM 渠道——然后让你的 Agent 开始干活。

## 配置说明

LambChat 支持通过 UI 和环境变量配置。从 `.env.example` 起步，面向真实用户使用前先设置稳定的密钥。

存储在数据库中的运行时设置优先于环境变量。环境变量仅在对应数据库设置尚未写入时，作为初始值或兜底值生效。

```bash
# 推荐：保证会话跨重启仍有效
JWT_SECRET_KEY=your-stable-secret-key

# 推荐：保证已保存的 MCP 配置跨重启仍可解密
MCP_ENCRYPTION_SALT=your-stable-encryption-salt

# 可选：MongoDB
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB=agent_state
MONGODB_USERNAME=admin
MONGODB_PASSWORD=your-mongo-password

# 可选：Redis
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=your-redis-password

# 可选：定时任务
ENABLE_SCHEDULED_TASK=true

# 可选：任务执行后端
TASK_BACKEND=arq  # local 或 arq
```

| 类别 | 控制什么 |
|---|---|
| Frontend | 默认 Agent、欢迎建议、界面偏好 |
| Agent | 调试模式、日志级别 |
| Model | 多供应商模型管理、单模型配置、渠道路由 |
| Session | 会话管理、消息历史、SSE 缓存 |
| Database | MongoDB 连接、可选 PostgreSQL |
| Storage | 持久化存储、S3/OSS/MinIO/COS |
| Security | 加密与安全策略 |
| Sandbox | Daytona、E2B、CubeSandbox 沙箱设置 |
| Skills | 技能系统配置 |
| Tools | 工具系统设置 |
| Tracing | LangSmith 与链路追踪 |
| User | 用户管理、注册、默认角色 |
| Memory | 原生记忆系统 |
| Scheduler | 动态定时任务与运行时注册 |
| Task Runtime | 本地执行或 arq 队列设置 |

## 开发指南

### 代码质量

```bash
make format       # ruff 格式化
make lint         # ruff 检查
make typecheck    # mypy 类型检查
make test         # 前端（vitest）+ 后端（pytest）测试
make check-all    # pre-commit hooks + 类型检查 + 测试 + 构建
```

### 前端、移动端与文档

```bash
cd frontend
pnpm run build             # TypeScript + Vite 构建
pnpm run packaged:build    # 构建打包版前端资产
pnpm run mobile:sync       # 构建并同步 Capacitor 工程
pnpm run package:desktop   # 打包桌面端资产

cd ..
pnpm run docs:dev          # VitePress 文档站
pnpm run docs:build
```

### 项目结构

```text
.
├── main.py                  # Uvicorn 入口，指向 src.api.main:app
├── src/
│   ├── agents/              # Quick、Search、Team Agent 图及共享 core 运行时
│   ├── api/                 # FastAPI 应用、中间件与路由模块
│   │   └── routes/          # Chat、auth、MCP、skills、files、scheduler、teams 等
│   ├── infra/               # 运行时服务：auth、llm、mcp、scheduler、task、storage、memory
│   └── kernel/              # 设置、schema、配置定义与共享类型
├── frontend/
│   ├── src/                 # React 应用源码
│   │   ├── components/      # Chat、panels、pages、auth、skill、MCP、team、file UI
│   │   ├── services/        # API 客户端与浏览器服务集成
│   │   ├── stores/          # 前端状态管理
│   │   ├── i18n/            # 多语言文件与测试
│   │   └── workers/         # 浏览器/PWA worker
│   ├── android/             # Capacitor Android 工程
│   ├── ios/                 # Capacitor iOS 工程
│   ├── src-tauri/           # Tauri 桌面端外壳
│   └── scripts/             # 前端构建、打包与 i18n 脚本
├── docs/                    # VitePress 文档
├── deploy/                  # Docker Compose 部署
├── k8s/                     # Kubernetes 清单
├── nginx/                   # 反向代理配置
├── scripts/                 # 沙箱与运维脚本
└── tests/                   # 后端、API、infra、agent 与单元测试
```

## Star History

<div align="center">

<a href="https://star-history.com/#Yanyutin753/LambChat&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=Yanyutin753/LambChat&type=Date" />
 </picture>
</a>

</div>

## 贡献者

<div align="center">

<a href="https://github.com/Yanyutin753/LambChat/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Yanyutin753/LambChat" alt="Contributors">
</a>

</div>

## 许可证

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

> **注意** — 项目名称 **"LambChat"** 及其 logo 不得更改或移除。

---

<div align="center">

<h3>🐑 LambChat</h3>

<p><em>部署一次，它就在任何时间、任何地点为你工作。</em></p>

<br>

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/Yanyutin753/LambChat">
        <img src="https://img.shields.io/badge/GitHub-181717?style=for-the-badge&logo=github&logoColor=white" alt="GitHub"><br>
        <sub>仓库</sub>
      </a>
    </td>
    <td align="center">
      <a href="mailto:3254822118@qq.com">
        <img src="https://img.shields.io/badge/Email-D14836?style=for-the-badge&logo=gmail&logoColor=white" alt="Email"><br>
        <sub>联系作者</sub>
      </a>
    </td>
    <td align="center">
      <a href="https://yanyutin753.github.io/LambChat/zh/">
        <img src="https://img.shields.io/badge/文档-0080FF?style=for-the-badge&logo=gitbook&logoColor=white" alt="Docs"><br>
        <sub>使用文档</sub>
      </a>
    </td>
    <td align="center">
      <a href="README.md">
        <img src="https://img.shields.io/badge/English-README-0052CC?style=for-the-badge&logo=readme&logoColor=white" alt="English README"><br>
        <sub>English README</sub>
      </a>
    </td>
  </tr>
</table>

<br>

<img src=".github/images/wechat-qr.webp" width="160" alt="微信二维码">

<br>

<sub>💬 欢迎交流部署、产品想法和合作，添加时备注 <strong>LambChat</strong></sub>

<br>

</div>
