# LambChat 开发指南

本文件是 LambChat 项目的开发指南。优先响应当前请求；当请求未提供特殊说明时，遵循以下项目约定。

## 项目概览

LambChat 是全栈 AI Agent 平台：

- **后端**: Python 3.12+, FastAPI, LangGraph/deepagents, MongoDB, Redis, arq。
- **前端**: React 19, TypeScript, Vite, TailwindCSS, PWA。
- **客户端**: Capacitor 移动端 App + Tauri 桌面 App。
- **文档**: VitePress，位于 `docs/`。

主要目录：

| 目录 | 用途 |
|------|------|
| `src/` | 后端代码 (agents, api, infra, kernel, skills) |
| `frontend/` | 前端代码 (Web + Mobile + Desktop) |
| `tests/` | Python 测试 (镜像 src/ 结构) |
| `deploy/` | Docker, Kubernetes 部署资源 |
| `docs/` | 项目文档站点 |

## 常用命令

```bash
# 安装依赖
make install-all

# 启动开发环境
make dev-all          # 同时启动前后端
make dev             # 仅后端
make frontend-dev    # 仅前端

# 构建
make build-all
make frontend-build

# 质量检查
make lint             # Ruff 代码检查
make typecheck        # Mypy 类型检查
make test             # 运行所有测试（前端 vitest + 后端 pytest）
make frontend-test    # 仅运行前端测试
make check-all        # 运行所有检查
```

前端专用命令：

```bash
cd frontend && pnpm run lint
cd frontend && pnpm run build
cd frontend && pnpm test           # vitest run（单次运行）
cd frontend && pnpm run test:watch  # vitest（watch 模式，TDD 开发核心命令）
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
- Python 代码遵循 `pyproject.toml` 中的 Ruff、Mypy、Pytest 配置。
- TypeScript/React 代码遵循 `frontend/package.json` 和 Vite/ESLint 配置。
- 面向用户的文案遵循现有的 i18n 结构，不要只更新一个 locale。
- 对 auth、RBAC、model keys、MCP secrets、文件访问、sandbox 执行等敏感路径，采用保守变更并添加验证。
- 不要随意重构无关代码，保持变更范围紧凑。
- 不要覆盖未提交的用户变更。

## 验证指南

根据变更范围选择最小验证方式：

| 变更类型 | 验证命令 |
|----------|----------|
| 前端逻辑 | `cd frontend && pnpm test` |
| 前端组件 | `cd frontend && pnpm test` + `cd frontend && pnpm run build` |
| 前端格式/类型 | `cd frontend && pnpm run lint` + `cd frontend && pnpm run build` |
| 后端逻辑 | `uv run pytest` (相关测试) |
| 后端格式/类型 | `make lint` + `make typecheck` |
| 跨栈变更 | `make check-all` |
| 文档变更 | 确认 Markdown 链接、命令和路径正确 |

如果验证因缺少服务、依赖或环境变量无法完成，明确说明。

## 本地开发地址

`make dev-all` 启动：

- 后端: `http://127.0.0.1:8000`
- 前端: `http://127.0.0.1:3001`
