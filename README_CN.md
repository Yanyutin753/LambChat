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

[English](README.md) | 简体中文

> 基于 FastAPI + deepagents 构建的生产级 AI Agent 系统

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

## 🏗️ 系统架构

<p align="center">
  <img src="docs/images/best-practice/architecture.png" alt="LambChat 系统架构" width="600"/>
</p>

## ✨ 核心特性

### 🤖 Agent 系统
- **deepagents 架构** - 编译图架构，支持细粒度状态管理
- **多 Agent 类型** - 核心 Agent（默认）、快速 Agent（速度优化）、搜索 Agent（网络搜索）
- **插件系统** - 使用 `@register_agent("id")` 装饰器快速注册自定义 Agent
- **流式输出** - 原生支持 SSE（Server-Sent Events）
- **子 Agent** - 支持多层级 Agent 嵌套
- **思考模式** - 支持 Anthropic 模型的扩展思考模式
- **代码解释器** - 内置代码执行与沙箱支持
- **人工审批** - 敏感操作的人工审批流程

### 🔍 网络搜索
- **搜索 Agent** - 搜索网页，返回标题、URL、摘要、网站图标等丰富结果
- **域名过滤** - 限制搜索结果到指定域名
- **时间范围过滤** - 按天/周/月/年过滤
- **区域支持** - 针对中国或海外区域优化
- **内容长度控制** - 平衡模式（400-600 字）或详细模式（2500 字）

### 🔌 MCP 集成
- **系统级 + 用户级 MCP** - 支持全局和个人 MCP 服务器配置
- **加密存储** - API Key 等敏感信息加密存储
- **动态缓存** - 工具缓存管理，支持手动刷新
- **多种传输协议** - 支持 stdio、SSE、HTTP 传输
- **权限控制** - 传输协议级别的访问权限

### 🛠️ 技能系统
- **双存储** - 文件系统 + MongoDB 双存储备份
- **访问控制** - 用户级别技能访问权限
- **GitHub 同步** - 支持从 GitHub 同步自定义技能
- **技能创建工具** - 内置技能创建工具包，含评估和基准测试
- **5 个技能槽** - 每个会话最多启用 5 个技能

### 💬 反馈系统
- **点赞评分** - 简单的正向/负向反馈
- **文字评论** - 详细的用户反馈
- **会话关联** - 反馈与具体会话/消息关联
- **运行级别统计** - 按运行聚合的反馈统计

### 📁 文档与文件支持
- **多格式预览** - PDF / Word / Excel / PPT / Markdown / Mermaid
- **图片查看器** - 内置图片预览，支持缩放
- **文件上传** - 拖拽或点击上传多个文件
- **云存储** - S3 / OSS / MinIO 集成
- **文件夹管理** - 将对话组织到文件夹中
- **会话搜索** - 全文搜索所有对话

### 🔄 实时与存储
- **双写机制** - Redis 实时写入，MongoDB 持久化存储
- **WebSocket 支持** - 实时双向通信
- **自动重连** - 断线后自动恢复对话
- **会话分享** - 支持公开或需登录的会话分享链接

### 🔐 安全与认证
- **JWT 认证** - 完整的认证流程，支持 Token 刷新
- **RBAC 角色** - Admin / User / Guest 三级角色
- **密码加密** - bcrypt 哈希加密
- **OAuth 支持** - 支持 Google、GitHub 等第三方登录
- **邮箱验证** - 安全的邮箱验证机制
- **沙箱执行** - 隔离的代码执行环境

### ⚙️ 任务管理
- **并发控制** - 任务执行队列，支持并发限制
- **任务取消** - 取消正在运行的任务
- **心跳监控** - 任务健康状态监控
- **发布/订阅** - 事件驱动的任务通知
- **状态追踪** - 实时任务状态更新

### 🔗 渠道与集成
- **飞书集成** - 原生支持飞书/Lark 平台
- **多渠道** - 可扩展的消息平台渠道系统
- **邮件服务** - 内置邮件通知支持
- **项目管理** - 按项目组织对话

### 📊 可观测性与管理
- **LangSmith 追踪** - 可选的 LangSmith 集成，用于 Agent 链路追踪
- **结构化日志** - 上下文感知的结构化日志
- **健康检查** - API 健康和就绪状态检查端点
- **用户管理** - 查看和管理用户
- **角色分配** - 配置每个角色可访问的 Agent

### 🎨 前端
- **现代技术栈** - React 19 + Vite + TailwindCSS
- **ChatGPT 风格** - 熟悉的对话界面体验
- **主题切换** - 深色/浅色模式，平滑过渡
- **国际化** - 多语言支持（英文、中文、日文、韩文）
- **响应式设计** - 移动端、平板、桌面端适配
- **Agent 切换** - 在核心/快速/搜索 Agent 间快速切换

## ⚙️ 配置说明

LambChat 支持 14 个设置分类，可通过设置页面或环境变量配置：

| 分类 | 说明 |
|------|------|
| **前端 (Frontend)** | 默认 Agent、欢迎建议、UI 偏好 |
| **Agent** | 调试模式、日志级别 |
| **LLM** | 模型选择、温度、最大 Token、API 密钥和基础 URL |
| **会话 (Session)** | 会话管理设置 |
| **数据库 (Database)** | MongoDB 连接设置 |
| **长期存储** | 持久化存储配置 |
| **安全 (Security)** | 安全策略和加密设置 |
| **S3** | 云存储（S3/OSS）配置 |
| **沙箱 (Sandbox)** | 代码沙箱设置 |
| **技能 (Skills)** | 技能系统配置 |
| **工具 (Tools)** | 工具系统设置 |
| **追踪 (Tracing)** | LangSmith 追踪配置 |
| **用户 (User)** | 用户管理设置 |
| **记忆 (Memory)** | 记忆系统（hindsight）设置 |

## 🛠️ 开发

### 环境要求
- Python 3.12+
- Node.js 18+
- MongoDB
- Redis

### 快速开始

```bash
# 克隆仓库
git clone https://github.com/Yanyutin753/LambChat.git
cd LambChat

# 复制环境变量文件
cp .env.example .env
# 编辑 .env 填写配置

# Docker 启动（推荐）
docker-compose up -d

# 或本地运行
make install  # 安装依赖
make dev      # 启动开发服务器
```

访问 `http://localhost:8000`

### 代码质量

```bash
# 格式化代码
ruff format src/

# 检查代码风格
ruff check src/

# 类型检查
mypy src/
```

### 项目结构

```
src/
├── agents/          # Agent 实现（核心、快速、搜索）
├── api/             # FastAPI 路由和中间件
├── infra/           # 基础设施服务
│   ├── auth/        # JWT 认证
│   ├── backend/     # 后端管理
│   ├── channel/     # 多渠道（飞书等）
│   ├── email/       # 邮件服务
│   ├── feedback/    # 反馈系统
│   ├── folder/      # 文件夹管理
│   ├── llm/         # LLM 集成
│   ├── memory/      # 记忆与 hindsight
│   ├── mcp/         # MCP 协议
│   ├── patches/     # 兼容补丁
│   ├── role/        # RBAC 角色管理
│   ├── sandbox/     # 沙箱执行
│   ├── session/     # 会话管理（双写机制）
│   ├── settings/    # 设置服务
│   ├── share/       # 会话分享
│   ├── skill/       # 技能系统
│   ├── storage/     # 文件存储
│   ├── task/        # 任务管理
│   ├── tool/        # 工具注册与 MCP 客户端
│   ├── tracing/     # LangSmith 追踪
│   ├── user/        # 用户管理
│   └── websocket/   # WebSocket 支持
├── kernel/          # 核心模型、配置、类型定义
└── skills/          # 内置技能（skill-creator）
```

## 🤝 参与贡献

我们欢迎任何贡献！请查看 [CONTRIBUTING.md](CONTRIBUTING.md) 了解指南。

## 📄 许可证

[MIT](LICENSE)

---

<p align="center">
  Made with ❤️ by <a href="https://github.com/Yanyutin753">Clivia</a>
</p>
