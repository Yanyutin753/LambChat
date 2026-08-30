# LambChat 开发指南

本文件是 LambChat 项目唯一的开发规范（single source of truth）。`CLAUDE.md` 等其他 Agent 指引文件只做转发，不要在别处复制维护本文件内容。

优先响应当前请求；当请求未提供特殊说明时，遵循以下项目约定。

## 项目概览

LambChat 是全栈 AI Agent 平台：

- **后端**: Python 3.12+, FastAPI, LangGraph/deepagents, MongoDB, Redis, arq。
- **前端**: React 19, TypeScript, Vite, TailwindCSS, PWA。
- **客户端**: Capacitor 移动端 App + Tauri 桌面 App。
- **文档**: VitePress，位于 `docs/`。

主要目录：

| 目录 | 用途 |
|------|------|
| `src/` | 后端代码 (agents, api, infra, kernel) |
| `frontend/` | 前端代码 (Web + Mobile + Desktop) |
| `tests/` | Python 测试 (镜像 src/ 结构) |
| `deploy/` | docker-compose 单机部署（`deploy.sh` + `docker-compose.yml`） |
| `k8s/` | Kubernetes/k3s 生产清单 |
| `docs/` | 项目文档站点 (VitePress) |

## 代码架构

### 后端分层结构

目录以仓库实际内容为准；新增/删除模块时同步更新本节。

```
src/
├── agents/            # Agent 图执行层
│   ├── core/          # BaseGraphAgent 基类、@register_agent 注册、AgentFactory（base.py）
│   ├── fast_agent/    # 快速 Agent
│   ├── search_agent/  # 搜索 Agent
│   └── team_agent/    # 团队 Agent
├── api/               # FastAPI 层
│   ├── main.py        # 应用入口（路由注册、生命周期）
│   ├── routes/        # 路由模块：chat、chat_sse、auth、session、mcp、skill、upload、settings、share、usage 等
│   ├── middleware/    # 全局中间件
│   └── deps.py        # 依赖注入
├── infra/             # 基础设施层：40+ 按业务域命名的包，常用的有
│   ├── agent/         # Agent 事件处理（events/processor.py）、任务管理
│   ├── auth/          # 认证授权
│   ├── chat/          # 会话消息处理
│   ├── llm/           # LLM 客户端（多 provider、多协议、请求头策略）
│   ├── mcp/           # MCP 工具管理、配置加密
│   ├── sandbox/       # 代码沙箱执行
│   ├── skill/         # 技能加载与市场（内置技能在这里，仓库已无 src/skills/）
│   ├── storage/       # MongoDB、S3、checkpointer
│   ├── task/          # arq 后台任务队列
│   └── …              # session、user、role、upload、search、notification、memory、share 等
└── kernel/            # 共享内核（不依赖 src/ 其他层）
    ├── config.py      # 全局配置定义
    ├── schemas/       # Pydantic 模型
    ├── types.py       # 类型定义
    └── exceptions.py  # 统一异常
```

### 前端结构

```
frontend/src/
├── components/        # React 组件（按功能分 20+ 子目录），常用的有
│   ├── chat/          # 聊天界面、消息渲染、工具面板
│   ├── panels/        # 侧边面板（MCP、技能、文件等；目录名是复数 panels）
│   ├── agent/         # Agent 选择器、模型配置
│   ├── pages/         # 页面组件
│   ├── sidebar/       # 侧边栏
│   └── …              # auth、common、persona、team、share、pwa、update 等
├── services/          # API 客户端（api/）、通知（notifications/）
├── stores/            # 状态管理
├── hooks/             # 自定义 Hook（含 useAgent 等）
├── i18n/              # 国际化文案
├── utils/             # 工具函数
├── contexts/          # React Context
├── constants/         # 常量
├── types/             # TS 类型
├── styles/            # 样式
└── workers/           # Web Worker（图片压缩、hash、剪贴板图片）
```

### Agent 执行流程

1. **请求接入** → API 路由接收消息，创建 `Presenter`
2. **Graph 执行** → Agent 通过 `BaseGraphAgent.stream()` 执行 LangGraph
3. **事件处理** → `AgentEventProcessor` 将 LangGraph 事件转换为 SSE 事件
4. **实时推送** → 通过 SSE/WebSocket 推送到前端
5. **状态持久化** → Checkpointer 保存到 MongoDB/PostgreSQL

### 关键设计模式

- **Agent 注册**：使用 `@register_agent("id")` 装饰器注册，通过 `AgentFactory.get()` 获取单例
- **Presenter 模式**：Agent 节点通过 `config["configurable"]["presenter"]` 输出 SSE 事件
- **Checkpointer**：LangGraph 状态持久化，支持 MongoDB（默认）和 PostgreSQL
- **任务队列**：arq 后台任务，支持本地和 Redis 执行

## 分支与发布流程

### 分支模型

```
feat/fix 分支 ──PR──▶ develop ──PR──▶ main ──▶ yang update.sh ──▶ 生产
                       │
                 CI 全量检查
                 出 develop-<时间戳> 镜像
                       │
                 update-staging.sh ──▶ staging 验证（yang 8021，仅 SSH 隧道可达）
```

| 分支 | 用途 | 保护 |
|------|------|------|
| `main` | 生产分支，每次合并出 `main-<时间戳>` 镜像 | 必须 PR；Merge Gate 只放行 `develop` 与 `hotfix/*` 来源 |
| `develop` | 集成分支（默认分支），所有 feature/fix PR 的目标，每次合并出 `develop-<时间戳>` 镜像 | 必须 PR（0 approvals，自合留痕即可） |
| `feat/*` `fix/*` `perf/*` `docs/*` `chore/*` | 短生命周期工作分支，从 `develop` 拉 | 无 |

### 提交信息规范

Conventional Commits + 中文描述：`类型(范围): 摘要`。

- 类型：`feat` / `fix` / `perf` / `refactor` / `docs` / `chore` / `test` / `ci`
- 范围可选，用模块名（如 `memory`、`api`、`frontend`）
- 示例：`fix(chat): 修复 /stream 路由被 helper 劫持`

### PR 规则

- feature/fix 一律 PR 到 `develop`（仓库默认分支）
- 标题同提交信息规范；关联 issue 用 `Closes #N`
- CI 绿（ruff / mypy / 前后端测试 / 镜像构建）后才可合并

### 镜像 tag 约定

| tag | 来源 | 用途 |
|-----|------|------|
| `develop-YYYYMMDD-HHmmss` | push `develop` | staging 验证 |
| `main-YYYYMMDD-HHmmss` | push `main` | 生产部署 |
| `v*` | 发版 tag | 归档 |

### 晋升 checklist（develop → main）

1. develop 上 CI 全绿
2. staging 验证：yang 上 `/data/lambchat-k8s/update-staging.sh` 滚到目标 tag，本地 `ssh -L 8021:127.0.0.1:8021 yang` 后访问 `http://127.0.0.1:8021` 真实跑一轮对话
3. 开 PR `develop` → `main`，合并（Merge Gate 会校验来源）
4. 生产部署：yang 上 `/data/lambchat-k8s/update.sh`（自动取最新 `main-*` tag，滚动失败自动回滚）
5. 部署后回归：`bash /root/disttest/run-all.sh`

### hotfix 流程

1. 从 `main` 拉 `hotfix/*` 分支修复（不能基于 develop，避免裹挟未验证改动）
2. PR 到 `main`（Merge Gate 放行 `hotfix/*`）
3. 生产恢复后，**必须**把同一修复回合（PR）到 `develop`，保持两分支不漂移

### 自动化贡献（巡检等）

自动创建的修复 PR 一律开向 `develop`，走同样的 staging 验证后晋升；禁止直接面向 `main`。生产部署永远人工执行（`update.sh`），自动化不得触碰。

## 常用命令

```bash
# 安装依赖
make install-all

# 启动开发环境
make dev-all          # 同时启动前后端
make dev              # 仅后端
make frontend-dev     # 仅前端

# 构建
make build-all
make frontend-build

# 质量检查
make lint             # Ruff 代码检查（全仓）
make format           # Ruff 格式化（全仓，含 Markdown 内代码块）
make typecheck        # Mypy 类型检查
make test             # 运行所有测试（前端 vitest + 后端 pytest）
make frontend-test    # 仅运行前端测试
make check-all        # 运行所有检查
```

前端专用命令：

```bash
cd frontend && pnpm run lint
cd frontend && pnpm run build
cd frontend && pnpm test               # vitest run（单次运行）
cd frontend && pnpm run test:watch     # vitest（watch 模式，TDD 开发核心命令）
cd frontend && pnpm run test:coverage  # 带覆盖率报告
```

## TDD 开发流程

### 红-绿-重构 (Red-Green-Refactor)

**核心原则：没有失败的测试，就不要写生产代码。**

```
1. RED    — 写一个失败的测试，描述期望行为
2. GREEN   — 写最少的生产代码让测试通过
3. REFACTOR — 在测试保护下清理和优化
```

**必须遵守：**
- 先写测试，再写代码。如果你先写了代码再补测试，那不是 TDD。
- 必须看到测试失败（RED）。测试直接通过说明测试可能写错了。
- 编写最小代码通过测试（GREEN）。不要在此阶段添加额外功能。
- 所有测试通过后才能重构（REFACTOR）。

### 前端 TDD: Vitest + @testing-library/react

```bash
# TDD 开发循环 — 在一个终端运行 watch 模式
cd frontend && pnpm test:watch
```

**测试分层策略：**

| 层级 | 工具 | 说明 |
|------|------|------|
| 工具函数 | Vitest expect | 纯函数，无需 DOM |
| Hook 逻辑 | Vitest expect | 提取纯函数测试，不直接测试 Hook |
| 源码结构 | Vitest toMatch | `*Source.test.ts` 验证代码结构模式 |
| React 组件 | @testing-library/react | 需要 jsdom 环境 |

**组件测试需要 DOM 时**，在测试文件顶部添加：

```ts
/** @vitest-environment jsdom */
```

**测试优先编写示例：**

```ts
// 1. RED — 先写测试
import { buildSubmitChatBody } from "../session";

test("includes user_timezone in submit body", () => {
  expect(buildSubmitChatBody({
    message: "hello",
    sessionId: "session-1",
    userTimezone: "Asia/Shanghai",
  })).toEqual({
    message: "hello",
    session_id: "session-1",
    user_timezone: "Asia/Shanghai",
    // ... 其他字段
  });
});

// 2. GREEN — 写最少代码通过测试
export function buildSubmitChatBody(opts: SubmitChatOpts) {
  return {
    message: opts.message,
    session_id: opts.sessionId,
    user_timezone: opts.userTimezone,
  };
}

// 3. REFACTOR — 优化、添加更多字段
```

### 后端 TDD: pytest

```bash
# 后端测试
make test              # 运行 pytest
uv run pytest tests/api/routes/test_chat.py -v  # 运行特定测试
uv run pytest --cov=src  # 带覆盖率
```

后端测试位于 `tests/`，镜像 `src/` 结构。使用 `pytest-asyncio` (asyncio_mode=auto)。

## 测试规范

### 测试位置

- **前端**: `frontend/src/**/__tests__/**/*.test.{ts,tsx}` — 与源码同目录的 `__tests__/` 子目录
- **后端**: `tests/` — 镜像 `src/` 结构

### 前端测试约定

```ts
// ✅ 好的测试
test("reconcileSessionList removes stale sessions", () => {
  expect(reconcileSessionList({
    previous: [session("keep"), session("drop")],
    latest: [session("keep")],
    removeMissing: true,
  }).map(s => s.id)).toEqual(["keep"]);
});

// ❌ 差的测试
test("test1", () => { /* 不清晰的测试名 */ });
test("works correctly", () => { /* 过于笼统 */ });
```

**约定：**
- 每个测试测一个行为
- 测试名描述期望行为，不是实现细节
- 优先提取纯函数测试（从组件/Hook 中提取逻辑到可测试的纯函数）
- 源码结构测试 (`*Source.test.ts`) 使用 `readFileSync` + `toMatch` 验证代码模式
- Fixture 内联在测试文件中，不使用共享 mock 文件

### 后端测试约定

- Fixtures 定义在 `conftest.py`
- 异步测试使用 `async def test_*` (pytest-asyncio 自动处理)
- Mock 使用标准 `unittest.mock` 或 `pytest-mock`

## 开发规范

- 编辑前先阅读现有模块，保持当前架构、命名和代码风格。
- Python 后端使用 `uv`，不要混用 `pip install`。
- 前端使用 `pnpm`，不要提交 `node_modules/` 或构建产物。
- Agent/工具生成的本地状态目录（如 `.mimosa/`、`.zcode/`、`.claude/`、`.codex/`）一律在 `.gitignore` 中按整目录忽略，不要按单文件零散追加条目，也不要提交。
- Python 代码遵循 `pyproject.toml` 中的 Ruff、Mypy、Pytest 配置；格式统一交给 `make format`（ruff），不要手工维持另一种风格。
- TypeScript/React 代码遵循 `frontend/package.json` 和 Vite/ESLint 配置。
- 面向用户的文案遵循现有的 i18n 结构，不要只更新一个 locale。
- 对 auth、RBAC、model keys、MCP secrets、文件访问、sandbox 执行等敏感路径，采用保守变更并添加验证。
- 不要随意重构无关代码，保持变更范围紧凑。
- 不要覆盖未提交的用户变更。

### Agent 开发

创建新 Agent：

```python
from src.agents.core import BaseGraphAgent, register_agent


@register_agent("my_agent")
class MyAgent(BaseGraphAgent):
    _agent_name = "My Agent"
    _description = "Description"
    _sort_order = 100

    def build_graph(self, builder):
        builder.add_node("agent", self.agent_node)
        builder.set_entry_point("agent")
        builder.add_edge("agent", END)

    async def agent_node(self, state, config):
        presenter = config["configurable"]["presenter"]
        presenter.present_text("Hello")
        return {"output": "done"}
```

### 统一错误码（Error Codes）

**规矩：后端所有面向前端的错误必须走 `src/kernel/errors.py` 的 `ErrorCode` 枚举 + `AppError`，禁止在路由层 `raise HTTPException`，禁止硬编码中文错误消息。**

- 错误响应契约：`{"detail": {"code": "<snake_case>", "message": "<英文兜底>", "args": {...}}}`，由 `src/api/error_handlers.py` 的全局处理器序列化；SSE 错误事件统一带 `code` 字段。
- 新增错误：在 `ErrorCode` 加 `(code, http_status, default_message)` 成员（消息用英文，插值写 `{{param}}` 并通过 `args={"param": value}` 传值），raise 处用 `raise AppError(ErrorCode.XXX, args={...})`；动态原文透传用 `message=str(e)`。
- 前端翻译：i18n key 为 `backendErrors.<camelCase(code)>`（如 `session_not_found` → `backendErrors.sessionNotFound`），**必须同步更新 zh / en / ja / ko / ru 五个 locale**，可运行 `uv run python scripts/sync_error_locales.py` 生成骨架后补翻。
- **CI 强制**：`frontend/src/i18n/__tests__/backendErrorCodeCoverage.test.ts` 校验五语全覆盖；`tests/api/test_no_http_exception.py` 禁止路由层 `raise HTTPException`。漏翻或绕过都会直接挂测试。
- 前端消费：`translateApiError(code, message, args, t)`（`frontend/src/utils/backendErrors.ts`），优先级「码翻译 > 原文映射/正则 > 原文」；error 对象带 `.code` / `.status` / `.args`。

### 内置系统工具（Internal Tools）

**规矩：后端每写一个内置系统工具，前端必须同步提供专属 Item，禁止落入通用 Wrench 图标兜底。**

- 工具定义位置：`src/infra/tool/`、`src/infra/memory/tools.py`、`src/infra/skill/skill_search_tool.py`。
- 前端在 `frontend/src/components/chat/ChatMessage/items/` 新建 `XxxItem.tsx`，参照 `ToolSearchItem` / `MemoryRecallItem` 的既有模式：`CollapsiblePill` + 专属 lucide 图标（size 12、`opacity-50`）+ inline 紧凑预览 + `openToolLivePanel` 实时面板，配色遵循 `themedToolItemsSource.test.ts` 的 accent 约定（风格高级、专业、简约）。
- 在 `MessagePartRenderer.tsx` 按 `part.name` 路由到该 Item，并在 `ToolCallItem.tsx` re-export。
- 面向用户的文案同时更新 zh / en / ja / ko / ru 五个 locale。
- **CI 强制**：`dedicatedInlineToolItemsSource.test.ts` 会自动扫描上述后端目录提取工具名（`@tool` 函数与 BaseTool 子类的 `name` 字段），任何缺少专属路由的新工具都会直接挂测试；新增工具时把名字补进该测试的基线清单。

### 环境配置

**必须配置的密钥（生产环境）：**

```bash
JWT_SECRET_KEY=              # JWT 签名密钥
MCP_ENCRYPTION_SALT=         # MCP 配置加密盐
```

**可选但推荐：**

```bash
MONGODB_URL=mongodb://localhost:27017
REDIS_URL=redis://localhost:6379/0
```

LLM 模型通过 **Model Config UI** 配置，无需在环境变量中设置 API Key（除非需要独立的标题生成模型）。

## 验证指南

根据变更范围选择最小验证方式：

| 变更类型 | 验证命令 |
|----------|----------|
| 前端逻辑 | `cd frontend && pnpm test` |
| 前端组件 | `cd frontend && pnpm test` + `cd frontend && pnpm run build` |
| 前端格式/类型 | `cd frontend && pnpm run lint` + `cd frontend && pnpm run build` |
| 后端逻辑 | `uv run pytest`（相关测试） |
| 后端格式/类型 | `make lint` + `make typecheck` |
| 跨栈变更 | `make check-all` |
| 文档变更 | 确认 Markdown 链接、命令和路径正确 |

如果验证因缺少服务、依赖或环境变量无法完成，明确说明。

## 本地开发地址

`make dev-all` 启动：

- 后端: `http://127.0.0.1:8000`
- 前端: `http://127.0.0.1:3001`
