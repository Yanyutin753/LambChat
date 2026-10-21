# LambChat 开发指南

本文件是 LambChat 项目唯一的开发规范（single source of truth）。`CLAUDE.md` 等其他 Agent 指引文件只做转发，不要在别处复制维护本文件内容。

优先响应当前请求；当请求未提供特殊说明时，遵循以下项目约定。

## Impeccable 前端设计规范

所有前端开发、UI 修改和视觉走查都必须先阅读仓库根目录的 `DESIGN.md` 与 `PRODUCT.md`。这两份文件记录 LambChat 的视觉系统、产品上下文和交互约束，是 Impeccable 项目级设计指导在本仓库的落地文件。

- 新增或修改 UI 前，先复用现有组件、主题 token、布局和 i18n 结构；不得另起一套颜色、字体、间距或圆角体系。
- 优先保证信息层级、可读性、响应式、键盘操作、无障碍、深浅色主题和加载/空/错状态；避免 AI 常见的无意义渐变、嵌套卡片、过度圆角、侧边标签、装饰性 emoji 和无目的动效。
- 面向用户的文案同步更新 zh / en / ja / ko / ru 五个 locale；动效尊重 `prefers-reduced-motion`。
- 修改后运行 `DESIGN.md` 的交付检查，并在环境允许时运行 `npx impeccable update` 或 Impeccable 检查器；检查器不可用时，按同一清单完成人工检查。
- 前端变更仍必须通过仓库既有的测试、lint、build 和类型检查，Impeccable 不能替代这些门禁。

## 项目概览

LambChat 是全栈 AI Agent 平台：

- **后端**: Python 3.12+, FastAPI, LangGraph/deepagents, MongoDB, Redis, arq。
- **前端**: React 19, TypeScript, Vite, TailwindCSS, PWA。
- **客户端**: Capacitor 移动端 App + Tauri 桌面 App，开发规范见根目录 `CLIENT.md`（含本地沙箱 daemon sidecar，为本文件在客户端领域的专项细化）。
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
│   ├── quick_agent/   # 快问快答 Agent
│   ├── search_agent/  # 搜索和执行 Agent（无沙箱时使用持久化文件后端）
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
│   ├── goal.py        # 单轮 Goal 评分；persistent_goal.py / goal_runtime.py / goal_continuation.py 承载会话目标与续跑
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
                 update-staging.sh ──▶ staging 验证（https://test.lambchat.com，SSH 隧道到 NodePort 30082 备用）
```

| 分支 | 用途 | 保护 |
|------|------|------|
| `main` | 生产分支，每次合并出 `main-<时间戳>` 镜像 | 必须 PR；Merge Gate 只放行 `develop` 与 `hotfix/*` 来源 |
| `develop` | 集成分支（默认分支），所有 feature/fix PR 的目标，每次合并出 `develop-<时间戳>` 镜像 | 必须 PR（0 approvals，自合留痕即可） |
| `feat/*` `fix/*` `perf/*` `docs/*` `chore/*` | 短生命周期工作分支，从最新 `origin/develop` 拉 | 无 |

### 开发起点（基于最新 origin/develop）

**工作区规矩：默认在当前本地分支开发，不创建 worktree；只有用户明确要求创建时才创建。不得因未提交改动、多对话协作或隔离需要自行创建 worktree，也不要主动要求用户改用 worktree。用户明确说不要建时，必须继续在当前本地分支处理。保留已有改动，不覆盖、不擅自 stash 或切换分支。**

多对话协作统一在当前本地分支开发，保留共享工作区中的已有改动，由一个对话统一做最终验证。

**规矩：任何开发开工前，先同步远端并基于最新的 `origin/develop` 进行——新分支直接从 `origin/develop` 拉，已有分支先 rebase 到 `origin/develop` 再继续；禁止基于过期的本地 `develop` 或其他工作分支开工。**

```bash
git fetch origin

# 开新工作分支：直接基于最新 origin/develop
git checkout -b feat/xxx origin/develop

# 已有分支继续开发 / 开 PR 前：先 rebase 到最新 origin/develop
git rebase origin/develop
```

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
| `v*` | 发版 tag（只打在 `main`） | 归档 + App Release 触发 |

### 发版节奏（防热修风暴）

**规矩：同一自然日最多发一个正式版。**当天发现的问题攒到 develop（P0 例外：生产不可用/数据丢失可即时热修）；出包后处于「烘焙态」，CI、产物冒烟、签名校验和自动化回归通过后再推给桌面端。Mac、Windows 及手机真机检查均为可选，不作为发布门槛；未执行时如实记录，不影响发布。

### Dev Release：下一版本预发布

- 预发布 tag 使用 `vX.Y.Z-dev.N`（如 `v2.15.2-dev.1`），`X.Y.Z` 是下一正式版，`N` 从 1 递增，最大 998。不得覆盖既有 tag 或复用同一编号。
- GitHub 必须标记 **Pre-release** 且 `make_latest=false`；稳定版 Latest、安装脚本、下载页和默认版本查询继续指向最近正式版。dev 版可通过指定 tag 的 Release 页面及主动选择测试版通道的下载页/客户端获取，不影响默认正式通道。
- 平台安装版本与服务端运行时继续使用数字核心 `X.Y.Z`；CI 将完整 tag 注入客户端前端及桌面更新比较（`RELEASE_TAG`）。更新排序为 dev.N 数值递增、同核心正式版高于所有 dev，不自动降级。签名清单保持核心版本并绑定完整资产名与源码 SHA。旧 dev.2 及更早包缺少完整构建身份，需手动重装一次支持更新通道的新版。
- 更新通道为设备级主动选择：默认 stable，dev 通道可获取已完成发布门禁的测试版及正式版。下载/安装期间禁止切换，切换后丢弃旧检查结果和待安装目标；所有下载绑定具体 tag。
- Android `versionCode` = `(major × 10000 + minor × 100 + patch) × 1000 + 构建序号`（minor、patch 均须小于 100，结果不超过 Android 的 2100000000 上限）：dev 使用 N，正式版使用 999。例如 `2.15.2-dev.1` 为 21502001，正式版为 21502999；iOS `MARKETING_VERSION` 使用核心版本，`CURRENT_PROJECT_VERSION` 使用对应构建序号。每次替换同核心包都须增加平台构建号。
- dev 包仍须通过完整 CI、各端打包、产物冒烟及签名校验，失败的预发布不得宣传为可用版本。正式版和测试版均不阻塞于真机检查，Release 如实说明尚未验证项和已知问题。标签遵守下文 main 合并提交规则；Web/服务端经 staging 验证后可独立部署生产，客户端 dev 发布不自动晋升稳定通道。
- dev 版无论 `DESKTOP_UPDATER_AUTO_PUBLISH` 配置如何，都禁止上传稳定 `latest.json`；手动 Desktop Updater Publish 继续拒绝 dev tag。App Release 仅在源提交 CI 与全部原生构建成功、资产签名上传完成后，最后发布独立 `dev-latest.json` 作为测试通道就绪标记。测试版查询不得选择缺少该标记的 dev；稳定缓存与测试缓存隔离。
- 验证完成后以新 `vX.Y.Z` tag 重新构建正式版，并重新签名、核验版本与升级路径；不得直接编辑 dev Release 将其改成正式版。正式发布仍遵守每天一个正式版与自动化验证要求，dev 预发布不占当天正式版名额。
- 版本优先级遵守 [SemVer](https://semver.org/)，GitHub 通道标记遵守 [Managing releases](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)。

### 发版流程（App Release / `v*` tag）

**规矩：发版 tag 一律打在 `main` 的合并提交上——hotfix 或 develop 晋升合入 `main`、CI 全绿后再打 tag；禁止在 feature 分支或未晋升到 `main` 的提交上发版。**

1. 打 tag 前先 bump 七处版本文件并保持一致：`frontend/package.json`、`frontend/src-tauri/tauri.conf.json`、`frontend/src-tauri/Cargo.toml`（编译期进 `CARGO_PKG_VERSION`，桌面运行时版本依赖它，漏 bump 会导致版本信息不一致）、android `versionName`/`versionCode`（按上文核心版本与构建序号映射）、iOS `MARKETING_VERSION`、`pyproject.toml`（服务端 `/api/version` 运行时读它，漏 bump 网页端版本号就不同步）、`client/lambchat_sandbox/__init__.py` 的 `__version__`（daemon 自更新比版本，漏 bump daemon 永不更新）——app-release.yml 的 preflight 会校验 tag 与版本一致，漂移直接红。
2. 在 `main` 合并提交上打 tag 并推送，触发 `app-release.yml`：六端矩阵构建（Linux x86_64/arm64、Windows、macOS Apple Silicon/Intel）+ Android/iOS，即发即传上传 GitHub Release。
3. 出包默认**烘焙态**：资产全部上 Release、CI 打包产物冒烟（mac 直接跑 .app 内 daemon、Linux 解包 deb 跑、Windows 跑 sidecar）须绿，但 `latest.json` **不上传**——桌面端自更新不感知。自动化回归通过后，到 Actions 手动跑 **Desktop Updater Publish**（输入 tag）才把 latest.json 推给桌面端；真机检查可选，不阻塞该步骤。发版完成仍要求 latest.json 平台条目齐全（Windows NSIS + 双架构 macOS，含 `darwin-x86_64`；Linux 不进清单——已停发 AppImage，deb/rpm 走应用内自研更新链路）。仓库变量 `DESKTOP_UPDATER_AUTO_PUBLISH=true` 可恢复随包直发（不建议）。
> 烘焙期间，`/api/version/assets/latest.json/download` 继续提供最近已发布的稳定版清单；带 `?tag=` 的下载仍严格锁定指定版本。仅桌面自动更新清单回退，普通安装包和移动端版本查询沿用最新 Release。

更新清单的 `notes` 与 `pub_date` 必须来自该 tag 的 GitHub Release 正文与发布时间，不能只填写产品名和版本号；桌面、Linux 与移动端均展示实际改动、日期及完整更新日志链接。

4. 正式版重打遵循现有人工流程；已发布 `dev-latest.json` 的测试版禁止覆盖，必须递增 dev.N。尚未就绪的 dev 构建可重试，发布工作流按 tag 串行并在上传前检查就绪标记。

### 晋升 checklist（develop → main）

1. develop 上 CI 全绿
2. staging 验证：yang 上 `/data/lambchat-k8s/update-staging.sh develop-YYYYMMDD-HHMMSS` 滚到已核验源码与 CI 的明确 tag，访问 `https://test.lambchat.com` 真实跑一轮对话（备用：本地 `ssh -L 8021:127.0.0.1:30082 yang` 后打开 `http://127.0.0.1:8021`；始终经过稳定 Service，不绑定交替使用的 API 端口）
3. 开 PR `develop` → `main`，合并（Merge Gate 会校验来源）
4. 生产部署：yang 上 `/data/lambchat-k8s/update.sh main-YYYYMMDD-HHMMSS`（显式指定已核验源码、CI 与 staging 的不可变 `main-*` tag；滚动失败自动回滚；脚本安装与发布约束见 `k8s/README.md`）
5. 部署后回归：`bash /root/disttest/run-all.sh`

### 每次客户端发版的自动化回归

- 正式版和测试版均在出包后运行 `make -j1 release-regression RELEASE_TAG=vX.Y.Z[-dev.N]`（填写实际 tag）。默认只运行既有生产自动化回归，包含桌面、Android、iOS 浏览器模拟下的图片直连、回退和私有鉴权；不连接或安装任何真机。
- Windows 真机脚本保留为显式调用的可选工具，Mac、Windows、手机真机未测均不影响发布。自动化、模拟、打包冒烟和真机结论分别记录，不把未测写成通过。
- 私有机器配置、依赖及操作步骤见 `scripts/release_tests/README.md`。报告保存在仓库外，每次使用独立运行编号；GitHub 托管 runner 不要求访问局域网真机，也不安装新的后台任务或自托管 runner。

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
  expect(
    buildSubmitChatBody({
    message: "hello",
    sessionId: "session-1",
    userTimezone: "Asia/Shanghai",
    }),
  ).toEqual({
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
  expect(
    reconcileSessionList({
    previous: [session("keep"), session("drop")],
    latest: [session("keep")],
    removeMissing: true,
    }).map((s) => s.id),
  ).toEqual(["keep"]);
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

### 真实 Agent、Goal 与定时任务验收

- 本地需要用户回看结果的验收使用 `desktop_dev` 账号，给新建对话和定时任务加明确的验收标题并保留结果；不修改或清理账号原有对话、设置及任务。无人值守验收结束后暂停本次创建的定时任务，回收临时 PAT、daemon 和工作目录；需要用户继续使用的沙箱连接及交付文件明确标识后保留，凭据只写入仓库外的私有目录。
- 复杂 Goal 使用公开题目或明确的业务任务，记录题目来源、模型与配置；通过真实沙箱完成规划、文件读写、代码执行、测试和评分，保存原始工具结果与最终状态。不得降低评分、证据或权限要求来制造完成结果。
- 缓存验收分别报告主 Agent、同一子 Agent、Goal 评分器和定时任务；区分首次请求、连续新轮次及完全相同输入的重复调用。推荐问题、历史摘要和后台记忆提取等图外辅助调用也须单列成本，历史未记录用量不能按零计。记录真实输入 token、缓存读取 token 和耗时，供应商缺少字段时标为未知；没有同条件对照时不宣称提速比例或与其他产品相同。
- 新 Goal 首评需与完全冷启动、同一历史换 Goal、评分重试分别测量；禁止用无任务意义的静态填充、隐藏预热请求、缓存评分结论或忽略摘要调用来抬高缓存率。调整评分输入布局时保留全部规则、冻结标准、转义及原始证据有效性检查；摘要复用原生历史时禁用工具执行，计入 system/tools 预算，并验证溢出回退、并发隔离和压缩后的上下文保留，覆盖主图与持续子图的实际组装入口。同一图内可复用完全相同输入的已生成摘要，重试键必须覆盖会话/线程、模型、system、tools、工具选择、设置和历史，且不得重复累计压缩提示。 摘要禁工具须验证实际协议参数：Anthropic 使用 `{"type":"none"}`，OpenAI Chat/Responses 使用 `"none"`，主请求原工具选择不变；仅靠提示词或没有本地执行循环不足以禁止供应商工具。
- 缓存优化不得改变消息语义：Goal 续跑轮号以服务端 `_continuation.turn` 为准，工具、待办、证据和状态更新不推进轮号；执行编号变化时，不重复追加已过期且内容未变化的证据索引，但仍执行 clock/scope 失效检查并追加新观察；持续子 Agent 的活动按本次执行归档，保留原 checkpoint 和历史日志，避免续聊时反复归档、压缩整段旧历史。 调整中间件 hook 或图节点时，同时验证旧 checkpoint 恢复；仍被持久化状态引用的节点需保留兼容入口。
- 执行工具也会使先前文件观察失效，即使测试通过也不能继续引用旧读取 ID。模型指引须明确：最后一次执行后重新读取最终报告所需的源文件，只引用当前 observed/verified 证据；修复重复验收不得放宽 clock/scope、冻结标准或原始证据检查。
- 沙箱工作目录元数据在实际系统消息拼装后仍须位于固定说明之后，后续角色发现、父/子对话提示不得把变化路径重新夹进固定前缀；保留全部说明、转义和调用方缓存策略，以真实中间件组合和最终协议请求体核验，不凭单个 hook 的“追加到末尾”推断完成。
- Anthropic 消息缓存断点复用截至该位置的完整前缀，不能按上一条回答或相邻断点间的字符数判断；工具前缀的最小缓存长度也交由供应商判断，不用固定字符阈值；断点跳过思考块和空文本。调用方在消息、工具或请求级显式提供 `cache_control` 时保留其策略，不叠加默认标记、覆盖 TTL 或突破四个断点上限；流式和非流式都核对最终协议请求体。协议修复不能替代当前供应商的真实缓存率测量。
- Search/Team 未指定思考强度时使用 medium，Quick 保持 low；目录声明、运行时缺省和偏好页须一致，保留用户显式选择及旧 off 值归一为 low 的兼容行为。复杂正确性评测须逐项核对不变量与反例，提示词包含规则、页面通过或提高思考强度均不能替代答案正确性证据；有歧义的字段另开明确版本，保留原题与原失败结果。
- 评分安全边界发生输入回放碰撞时，替代候选也应由服务端密钥按独立域确定生成并逐一检查全部输入；保持无碰撞旧字节兼容，不得以随机刷新边界破坏相同请求的可复用前缀。边界稳定性修复不能宣称提升未经重新实测的全新 Goal 首评缓存率。
- 记忆导航索引随 `task_context` 追加到 checkpoint，不得通过动态 `memory_recall` 工具描述破坏前缀。每次调用重新走作用域及现有失效缓存；仅本次已授权工具包含 `memory_recall` 才能读取/注入，空快照明确替代旧索引，保留旧 checkpoint 节点的恢复兼容。
- 后台记忆候选须兼容自定义 `session_id` 与普通 MongoDB `_id`，按会话存储相同优先级归一化后关联 trace 与任务；不得丢弃没有自定义 ID 的正常会话，仍须保留所有者、空闲窗口、隐藏/定时排除及运行中 trace 检查。
- 项目记忆反查同样先查自定义会话 ID，仅在没有对应文档时回退普通 `_id`；已有自定义会话没有项目时不能误用另一文档的项目。明确的记忆质量或输入校验拒绝须以结构化重试标记终止重复提取，保留失败原因与真实模型消耗，不降低质量门槛或计为成功写入；存储/网络异常仍保留重试。
- 独立后台记忆提取任务须用空 `contextvars.Context()` 启动，显式传入所有者，不能继承前台图的回调、session/thread、presenter 或运行守卫；仅断开 LangSmith parent 不足以隔离 LangChain 配置。历史辅助用量的归属风险不能凭新修复自动重算为已知费用。独立推荐问题任务同样使用空上下文，仅显式携带所有者与会话/run/trace 归属，不能继承前台回调、线程或 Goal 执行守卫。 推荐历史投影须排除 user/human 角色中 `name=evidence_context` 且 `lambchat_evidence_snapshot is True` 的服务端快照，避免把证据索引当用户问题并挤掉真实历史；保留未标记旧消息、数值 1、其他命名消息及用户引用的相似文字，不修改 checkpoint 或评分原始证据。
- 用量完整性须贯穿模型聚合、SSE、接力/审批/重启恢复、历史落库和面板；显式缓存零须保留，缺字段或缺适用缓存单价不得按免费计价。旧记录无完整性证书时保留原始估算但不计入已确认总额；部分已知金额标示未知部分，全部未知显示占位。历史补价须按原模型、计数、完整性与未计价状态条件更新，分页不能被首批未知记录阻塞。 费用补价、条件写入、聚合、API 列表与聊天展示均须严格认证 `input_includes_cache is True`，数值 1 不算认证；原始估算保留但不得计入已知总额，认证在解析价格期间失效时不得写入已知费用。取消先终结而用量后到时，保留终态并刷新用量日志，以 trace 事件修订号阻止旧异步快照覆盖新用量；仅成功落库后通知。恢复快照的完整标记不能覆盖缺失、bool 或负数计数，未认证 inclusive input 不确认费用。
- 同一 Presenter 的内外模型事件共用原生 UUID 用量账本；中间快照不能完成尚未结束的调用，异步计价/写入期间新到的用量不得被旧快照标为已发送。快照须一致，运行时接力保留账本身份避免重复 seed，身份不进入 SSE；缺失或部分 token 数在页面显示未知，已知零保留。
- 缓存读取率与费用、缓存写入及四类占比完整性分别判断。缺写入量时，明确 read=0 且 input>0 可显示 0%；正读取率只有全部实际调用均有规范化的 inclusive input/read 口径认证才能显示；认证贯穿接力、审批恢复、SSE 与历史。原始供应商 fallback 和旧无认证记录保守保留未知，已知 0% 仍显示，未知说明原因，不补造零费用。
- LLM 异常分类须覆盖当前 SDK 实际使用的传输库（含 `httpx` / `httpx2`），保持瞬态断流可重试、鉴权失败不可同凭据重试；真实模型失败且缺用量时，Goal 总成本记为未知，保留已知下界，不能将失败尝试当作零成本。
- 思考强度须验证实际协议请求体，不得只验证 UI 选项；保留未配置调用方的供应商默认值。明确因输出额度耗尽而截断时，不以相同预算原样重试，保留原响应、已发生费用及既有备用模型/终态判定。 用户错误文案按实际原因区分输出上限和空回复，未发生重试时不得声称已经多次重试。不得将完整 `agent_options` 或解析后模型配置直接写日志，其中可能含请求头和自定义敏感数据。主模型只有思考且耗尽输出、没有新真实进展时，Goal 不得再自动派发同预算空转；评分器、摘要、推荐与子代理的耗尽不得冒充主模型失败，成功备用响应或新工具进展仍按原规则判定。
- 未配置的 GLM-5.3 增强推理输出预算使用原生 64K，保留显式 max_tokens、low 与旧模型行为；声明的小输入窗口须保留摘要输入余量。发出了 thinking.budget_tokens 不代表供应商实际按该字段截断，须核对原生 output/stop_reason；预算调整不能替代默认 medium 的真实正确性、辅助用量及长上下文验收。
- 真实验收被取消或暂停后保留终态，不自动恢复或换会话重放同一付费任务。验收脚本须在后续供应商调用前复核冻结源码，发生变化时停止新增付费调用并保留原因；结束后的源码差异检查不能替代这个门槛。页面费用验收核对实际金额、占位符及估算标记，不能把“费用总计”标签存在当成金额已确认。
- Goal 用量和后台所有权守卫必须覆盖实际内层模型图，不能只接基类入口；Search/Team 自定义流和隔离图显式传入执行守卫，不能恢复继承父任务的 checkpoint/流式回调。持续子会话须保留同一守卫且用量只计一次；活动轮次用 SSE 或活动 trace 验收，普通历史接口只含已完成轮次。
- 定时提示须明确区分稳定的 task 与每次变化的 run：新 run 继续本任务历史，不能从任务名称猜测既往结果；真实多轮验收同时核对实际输出和历史输入，不能只看调度状态 success。
- 取消请求等待执行任务时，须区分执行任务已取消与请求调用方自身取消；前者返回正常取消结果，后者继续传播。取消验收同时检查 HTTP 返回、SSE/持久化终态及并行 run 隔离，不能只凭一条 cancelled 事件认定成功。
- 关闭时仅可对同一 run 的活动状态原子写入可恢复失败；任务协程尚未退出不能证明它仍在运行，不得重启已完成、失败、取消或等待人工的 run。恢复先核验当前 Goal，再按 run 与独立 claim token 交接；最终接单前保留原 trace 和终态流，接单准备与 Goal 控制、新人类消息共享会话围栏。永久 admission 拒绝停止该 claim 重试，存储或网络故障仍可重试；晚到回滚不得覆盖新 claim、终态或原始错误取证。覆盖本地和 ARQ 两条路径，以及原 Goal 完成后普通人类续聊的恢复。
- 活动日志收据只允许真实写入成功后由服务端生成；主代理与子代理模型自写收据必须在 SSE 与最终 checkpoint 前清除路径并保留无路径说明，实时与最终结果共用规则，覆盖跨 chunk、工具块、断流重试和并行隔离。摘要流、摘要生成保存及历史显示投影同样覆盖，摘要尾部不得误发为主正文或计入 output_text；根流释放普通前缀尾部时须与 output_text 一致且只计一次；子代理归档替换根响应清理器，不得再次过滤服务端成功写盘后追加的真实收据；签名思考原文保留，只做历史显示投影。
- 评分请求的临时视图须保持已发送的历史前缀；可从首次评分起将服务端标记的索引槽位固定投影为相同引用，并在历史之后保留最新索引，但不得在续轮才将此前完整发送的旧索引改写为占位文字。保留消息位置、最新索引、原始证据及全部评分规则；不改 checkpoint 历史，用户消息与未获服务端认证的同名消息保守保留。不得直接删消息导致上游尾部窗口回填别的历史；移出的最新索引仍须执行原长度限制、转义及边界碰撞检查。
- 评分原始证据的短且完整记录可在校验后临时去掉重复 JSON 字符串编码，保留全部原文、checkpoint 来源和控制帧转义；大记录保留原截断字节。压缩评分证据时保留原消息槽数和未变化分块边界，避免尾部窗口回填更旧历史；不得把较小输入或同历史新 Goal 的缓存结论冒充完全冷启动首评提升。
- 常规实现、调试和已授权测试自主迭代，不重复询问；本地分支、已有改动保护及下文串行验证规矩继续适用。真实沙箱、浏览器、staging、生产及原生客户端的验证结论分别报告。
- 处理跳过测试时逐项补足真实条件：MongoDB 用例通过 `LAMBCHAT_MEMORY_MONGO_TEST=1` / `TEST_MEMORY_MONGODB=1` 启用，Redis 租约与进程恢复用例需要可启动隔离实例的 `redis-server`，E2B 用例需要真实供应商凭据；Windows ACL 用例必须在原生 Windows/NTFS 上执行。跨机测试复制原样源码、测试及 `scripts/run_validation.py` 并校验哈希，使用目标机器自己的共享验证锁；不得伪造平台、改掉 skip 或以另一种沙箱替代供应商测试后声称通过。

### 先改完再验证（跨对话协作）

**规矩：先完成当前请求的全部代码改动，以及调用方、测试、配置和相关 worktree 的同步，再运行 build、lint 等最终验证。禁止边改边反复构建、提前排队验证，或多个对话对同一批改动重复跑验证。TDD 的定向红绿测试仍按开发流程执行。**

- 跨对话协作时，先把可独立完成的改动做完；不要为等待其他对话结束、等待构建锁或反复查询其他对话状态而长期挂起。
- 验证名额被其他对话占用时，直接说明占用及尚未验证的项目并交付当前改动，留到该批改动全部完成后由一个对话统一串行验证；不得后台排队、循环重试或终止其他对话的任务。
- 复用其他对话的验证结果时，必须确认覆盖相同代码状态和变更范围，并注明来源；验证后代码再有修改，相关结果不再视为最终验证。全部改动稳定后再补一次必要验证，不重复跑无关全量检查。

### 本机验证必须串行（并发上限固定为 1）

**规矩：同一台机器上，LambChat 的 build、E2E、test、lint、format、typecheck 等构建与验证任务合计最多运行一个，覆盖所有会话、Agent、终端及 worktree。不同类别也不得同时运行；前一个任务彻底退出后，才能启动下一个。**

- 禁止通过后台 `&`、`Promise.all`、并行工具调用、多个终端或子 Agent 同时启动这些任务；已有任务运行时直接报告占用并退出，不跨对话排队等待，不重复启动，不擅自终止其他会话的任务。启动前检查运行中的构建/验证进程；检查进程只是协作约束，不能替代跨进程互斥锁。
- 工具支持 worker/job 配置时固定为 `1`，禁止自动按 CPU 核数扩展：Make 使用 `make -j1 <目标>`（含 `check-all`）；Vitest 使用 `pnpm test --maxWorkers=1 --no-file-parallelism --maxConcurrency=1`（watch/coverage 同样追加这些参数）；pytest 不使用 xdist 的 `-n` 或分片并跑；Ruff 使用 `RAYON_NUM_THREADS=1`；Rust/Cargo 使用 `CARGO_BUILD_JOBS=1`。ESLint 不启用并发选项。
- build、E2E、test、lint、typecheck 按顺序执行，发现失败先处理，再继续。watch 测试也占用这个唯一名额，退出后才能运行其他验证。
- E2E 脚本一次只运行一个；脚本为验证并发行为而必需的并发用例及 `--stress` 覆盖仍须保留，不能为了串行调度删减测试。
- 实际互斥入口为 `python3 scripts/run_validation.py <command> [args...]`，使用当前 OS 用户的 `~/.cache/lambchat/validation.lock`，所有 worktree 共用；占用时立即退出（退出码 75），不无限等待；任务退出后由 OS 释放锁，嵌套命令复用当前名额。Make/pnpm 验证入口、直接 pytest 和仓库沙箱 E2E 已接入。直接调用 Ruff、Mypy、Cargo、Vite 等底层命令时必须显式通过该入口，禁止绕过。
- 这里约束任务调度及工具公开支持的 worker/job 数，不保证构建工具、原生库或被测服务内部只有一个 OS 线程；不能拦截绕过入口的底层命令，也不跨 OS 用户或机器互斥。

根据变更范围选择最小验证方式：

| 变更类型 | 验证命令 |
|----------|----------|
| 前端逻辑 | `cd frontend && pnpm test` |
| 前端组件 | `cd frontend && pnpm test` + `cd frontend && pnpm run build` |
| 前端格式/类型 | `cd frontend && pnpm run lint` + `cd frontend && pnpm run build` |
| 后端逻辑 | `uv run pytest`（相关测试） |
| 后端格式/类型 | `make lint` + `make typecheck` |
| 跨栈变更 | `make check-all` |
| 本地沙箱/daemon/传输链路 | `uv run python scripts/e2e_local_sandbox.py`（详见下方规矩） |
| 云端沙箱暂停恢复（部署后，在可 kubectl 目标集群的机器上跑） | `python3 scripts/verify_sandbox_pause_heal.py --base-url <URL> --namespace <ns> --deployment <deploy> --user-id <uid>`（显式 pause→无感恢复；local 平台自动 SKIP；staging 可用 `--register` 一次性用户）；跨对话补充：`python3 scripts/verify_sandbox_cross_session.py`（同用户双会话×暂停交织，验隔离/共享/不重建） |
| 桌面端 Linux 更新链路 | `uv run python scripts/e2e_linux_update.py`（Rust 检测/下载单测 + 本机检测冒烟 + 前端契约） |
| 文档变更 | 确认 Markdown 链接、命令和路径正确 |

如果验证因缺少服务、依赖或环境变量无法完成，明确说明。

### 本地沙箱链路 E2E（平台开发硬性门禁）

**规矩：凡涉及本地沙箱链路的开发——`src/infra/sandbox/`、`client/lambchat_sandbox/`、`src/api/routes/sandbox.py`、请求体门限/传输相关中间件、桌面端 daemon 托管（`frontend/src-tauri/src/daemon.rs`）——合并前必须在本机跑通全量 E2E：**

```bash
uv run python scripts/e2e_local_sandbox.py             # 功能链路（全项须 PASS）
uv run python scripts/e2e_local_sandbox.py --stress    # 发版前/大改动追加压测段
```

- 脚本自举环境：后端未起会自动拉起（8000 被占时可用 `E2E_SANDBOX_SERVER` 指向自备实例）、注册一次性测试用户并铸 PAT、拉起 daemon，结束自动回收（测试用户/PAT/工作目录），只要求本机 MongoDB/Redis 可达（凭据读 `.env`）。
- 覆盖面：SSE 握手与多机注册表、exec 往返、机器绑定防冒答（409）、双向流式大文件传输（10/50/100MB sha256 校验）、结构化 fs op、分块 base64 兜底、优雅下线秒级翻转、skills 虚拟挂载 glob 递归契约（真实 MongoDB）、transfer_path 大批量整树搬运（真实 daemon）；`--stress` 追加并发扫描与持续负载。
- 这条门禁的由来：`fs_upload_stream` 分发漏注册（上传快路径整条失效）与请求体门限误伤流式回传（>8MiB 下载全灭）两个生产级 bug，都是单测/seam 全绿下只有该 E2E 抓到的。

## 本地开发地址

`make dev-all` 启动：

- 后端: `http://127.0.0.1:8000`
- 前端: `http://127.0.0.1:3001`
