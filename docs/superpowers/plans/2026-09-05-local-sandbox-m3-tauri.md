# 本地沙箱 M3（Tauri sidecar + 前端本地模式）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** daemon 封装进 Tauri 壳（sidecar 随壳分发/启停/更新），网页端出现"本地沙箱"完整体验：配对向导、状态灯、会话级云端/本地选择器。

**Architecture:** Tauri v2（2.11.2）最薄壳新增：PyInstaller 单文件 daemon 二进制经 `bundle.externalBin` 打入 → Rust `tauri-plugin-shell` sidecar 托管生命周期（启动/崩溃重启 3 次上限/退出清理）→ 自定义 invoke 命令（配对落盘/写配置/启停/开目录）→ 前端 ProfilePreferencesTab 新"本地沙箱"分区 + 会话沙箱选择器（agent_options.sandbox）。daemon 数据继续放 `~/.lambchat/`（不在 app_data_dir，规避升级清理）。

**Tech Stack:** PyInstaller（dev 依赖新增）、Rust（tauri-plugin-shell/tauri-plugin-opener、tray-icon feature）、React/TS（既有模式：SelectRow/ToggleSwitch/useTodayUsageCost 轮询）。

**Spec:** `docs/superpowers/specs/2026-09-01-local-sandbox-design.md` §5（Tauri 壳集成）§6（前端）§0 版本管理行。

## Global Constraints

- 工作目录：**全程在 worktree `/home/yangyang/LambChat/.worktrees/sandbox-m2-client`**（分支 feat/local-agent-desktop；主工作区被并行会话占用，禁止在那执行 git）。
- 面向用户文案 zh/en/ja/ko/ru 五语全量（`frontend/src/i18n/locales/*.json`，`scripts/extract-i18n.ts` 校验 t() key 一致性）；agent 选项文案走 `agentOptions.sandbox.*`。
- daemon 的 Python 代码（client/）**本里程碑不改业务逻辑**（bug 修复除外）；M3 是壳与 UI 层工作。
- Rust 侧验证 = `cargo build`（在 src-tauri 内）+ T8 冒烟；仓库无 cargo test 基建，不引入。
- CI（app-release.yml）改动只做语法/结构级验证 + 本地 Linux x64 实测打包，完整矩阵验证留 M4。
- 提交信息 Conventional Commits 中文。

## 关键技术事实（已核实，实现时直接用）

- sidecar：`tauri.conf.json` `bundle.externalBin: ["binaries/lambchat-daemon"]`，二进制命名 `lambchat-daemon-<target-triple>`（如 `x86_64-unknown-linux-gnu`）；Rust 端 `tauri_plugin_shell::process::Command::new_sidecar("lambchat-daemon")`，插件 `.plugin(tauri_plugin_shell::init())`。
- capabilities/default.json 现为 `["core:default","notification:default","updater:default"]`，需加 shell sidecar scope 与 opener 权限。
- lib.rs 现状（53 行）：`clean_on_version_upgrade` + builder（无 invoke_handler）；`clean_on_version_upgrade` 只清 app_data_dir——daemon 数据在 `~/.lambchat/`，天然安全，勿把 daemon 数据挪进 app_data_dir。
- 前端壳内检测：`isNativeAppRuntime()`（frontend/src/services/api/config.ts:84）、`detectPlatform()`（frontend/src/hooks/useAutoUpdate.ts:9）。
- agent_options 链路：`useAgentOptions.ts:47-79` 的 `normalizeAgentOptions` 有 enable_thinking 特判先例；提交拼装 `useAgent.ts:548-551` → `session.ts:124`（buildSubmitChatBody）；会话恢复 `useAgent/sessionConfig.ts:6-31`。
- 选项 UI：`ChatInputSelectors.tsx:208-231`（AgentOptionButton）、`ChatInputToolbar.tsx:186-192`（布尔型）。
- 设置 UI：`ProfilePreferencesTab.tsx`（卡片 L350 起；SelectRow L64-160；inline toggle L359-384；可复用 `panels/AgentPanel/shared/ToggleSwitch.tsx`）。
- 轮询范本：`hooks/useTodayUsageCost.ts:44-53`（interval + in-flight 去重 + 自定义事件刷新）。
- 打包链：`frontend/scripts/package-desktop.mjs`（pnpm dlx tauri build）；CI `.github/workflows/app-release.yml` L121-129 desktop 构建步（前插 daemon 构建步）；Linux 依赖已含 `libayatana-appindicator3-dev`（托盘 OK）。
- dev 回退（已裁决）：环境变量 `LAMBCHAT_DAEMON_BIN` 指向外部可执行（如 uv 包装脚本）时，Rust spawn 它而非 sidecar；两者皆无 → 不 spawn，前端显示"未运行"引导。**`tauri dev` 下 externalBin 二进制缺失不影响 dev 启动**（只在 new_sidecar().spawn() 时失败）。
- updater 已配 `createUpdaterArtifacts: true`——sidecar 进包后自动随更新分发，无需额外处理。

## File Structure

```
client/pyinstaller.spec                  # 新：daemon 打包 spec
client/scripts/build-daemon.sh           # 新：host triple 探测 + pyinstaller 调用 + 产物改名
Makefile                                  # 改：client-build-daemon 目标
pyproject.toml                            # 改：dev 组加 pyinstaller
frontend/src-tauri/Cargo.toml            # 改：+shell/+opener 插件、tray-icon feature
frontend/src-tauri/tauri.conf.json       # 改：+externalBin
frontend/src-tauri/capabilities/default.json  # 改：+shell scope/+opener
frontend/src-tauri/src/lib.rs            # 改：daemon 生命周期 + invoke_handler + 托盘
frontend/src-tauri/src/daemon.rs         # 新：DaemonManager（spawn/重启计数/kill/状态）
frontend/src/services/api/sandbox.ts     # 新：getSandboxStatus() 封装
frontend/src/hooks/useSandboxStatus.ts   # 新：轮询 hook（10s）
frontend/src/services/tauri/sandboxShell.ts  # 新：invoke 封装（壳内检测+降级）
frontend/src/components/profile/tabs/ProfilePreferencesTab.tsx  # 改：+本地沙箱分区
frontend/src/components/chat/ChatInputSelectors.tsx  # 改：沙箱选择器 + 在线点
frontend/src/hooks/useAgentOptions.ts    # 改：normalizeAgentOptions 注入 sandbox 选项
frontend/src/i18n/locales/{zh,en,ja,ko,ru}.json  # 改：profile.localSandbox.* / agentOptions.sandbox.*
.github/workflows/app-release.yml        # 改：daemon 构建步（双架构）
tests/client/test_packaging.py           # 新：spec/脚本结构测试
frontend/src/components/profile/__tests__/localSandboxSection.test.tsx  # 新（按仓库前端测试惯例）
```

---

### Task 1: PyInstaller 打包 daemon

**Files:** Create `client/pyinstaller.spec`、`client/scripts/build-daemon.sh`；Modify `pyproject.toml`（dev + `pyinstaller>=6.0`）、`Makefile`（`client-build-daemon:`）；Test `tests/client/test_packaging.py`

**Interfaces:**
- `build-daemon.sh`：探测 host triple（`rustc -vV` 的 host: 行，无 rustc 则 `uname -m` 映射）→ `uv run pyinstaller client/pyinstaller.spec --distpath client/dist` → 产物改名复制到 `frontend/src-tauri/binaries/lambchat-daemon-<triple>`（mkdir -p）
- spec：`Analysis(['client/lambchat_sandbox/__main__.py'], ...)` onefile、name `lambchat-daemon`、console=True、hiddenimports 无需（纯 stdlib+httpx 可自动发现）

**Steps:**
- [ ] Step 1: pyproject dev 组加 pyinstaller（`uv add --group dev pyinstaller` 或手编辑 + `uv sync`）
- [ ] Step 2: 写失败测试 `tests/client/test_packaging.py`：读 `client/pyinstaller.spec` 断言 onefile/name/入口路径三要素；读 `client/scripts/build-daemon.sh` 断言含 triple 探测与目标路径 `frontend/src-tauri/binaries/lambchat-daemon-`；读 Makefile 断言 `client-build-daemon` 目标存在（纯文件结构断言，风格参照仓库 `*Source.test.ts` 思路）
- [ ] Step 3: RED 确认 → Step 4: 实现 spec + 脚本 + Makefile → GREEN
- [ ] Step 5: 真实打包验证：`make client-build-daemon` → 产物存在且 `frontend/src-tauri/binaries/lambchat-daemon-<triple> --help` 不可直接跑（pyinstaller onefile 的 argv0）→ 用 `./lambchat-daemon-<triple> version`（cd 到 binaries）验证输出 `0.1.0`
- [ ] Step 6: `.gitignore` 加 `frontend/src-tauri/binaries/`（构建产物不入库）+ Commit `feat(sandbox): daemon PyInstaller 打包（sidecar 产物管线）`

### Task 2: Tauri sidecar 接线与生命周期

**Files:** Modify `frontend/src-tauri/Cargo.toml`（`tauri-plugin-shell = "2"`、`tauri` features + `"tray-icon"`）、`tauri.conf.json`（bundle + `"externalBin": ["binaries/lambchat-daemon"]`）、`capabilities/default.json`；Create `src/daemon.rs`；Modify `src/lib.rs`

**Interfaces（Rust）:**
```rust
// daemon.rs
pub struct DaemonManager { child: Mutex<Option<tauri_plugin_shell::process::CommandChild>>,
                           restarts: AtomicU8 }
pub fn start(app: &AppHandle) -> Result<(), String>
  // 优先 env LAMBCHAT_DAEMON_BIN（std::process::Command 直接 spawn，工作目录无关）；
  // 否则 Command::new_sidecar("lambchat-daemon").spawn()
  // spawn 后 tokio::spawn 监视 child：意外退出且 restarts<3 → 重启并 +1；正常 stop 不重启
pub fn stop(manager: &State<DaemonManager>)  // kill child，重启计数归零
pub fn status(manager: &State<DaemonManager>) -> String  // "running"|"stopped"|"unsupported"
```
- lib.rs：`.plugin(tauri_plugin_shell::init())`；setup 里 `app.manage(DaemonManager::default())` + `daemon::start(app)`（失败仅 log warn 不阻塞壳启动）；窗口关闭→app exit 事件里 `daemon::stop`
- capabilities：permissions 追加 `"shell:allow-execute"` + `"shell:default"`；`"windows"` 保持 `["main"]`

**Steps:**
- [ ] Step 1: Cargo/conf/capability 修改
- [ ] Step 2: 实现 daemon.rs + lib.rs 接线（Rust 侧无测试基建，验证=cargo build）
- [ ] Step 3: `cd frontend/src-tauri && cargo build` 通过（需要系统 rustc——本机有，探索已确认 package-desktop.mjs 校验过）
- [ ] Step 4: dev 冒烟：先 `make client-build-daemon` 产 sidecar → `LAMBCHAT_APP_URL=http://127.0.0.1:8000 pnpm tauri dev`（或 `pnpm dlx @tauri-apps/cli@2.11.2 dev`）——壳起、后端 status 转在线、关壳后 offline；若 tauri dev 环境不可用（缺系统 webview 依赖），记录并以 `cargo build` + 代码审查 + T8 兜底，报告说明
- [ ] Step 5: Commit `feat(sandbox): Tauri sidecar 接线与 daemon 生命周期托管`

### Task 3: Tauri 命令（配对/配置/启停/开目录）+ opener

**Files:** Modify `Cargo.toml`（+`tauri-plugin-opener = "2"`）、`lib.rs`（invoke_handler 注册）、`daemon.rs`；capabilities + `opener:allow-open-path` 精确 scope（限定 `~/.lambchat/**`——按 opener 插件 scope 语法写，若不支持目录通配则允许默认 opener 权限并在命令内自行校验路径前缀）

**Interfaces:**
```rust
#[tauri::command] fn save_pairing(server_url: String, pat: String, confirm_policy: String) -> Result<(), String>
  // 写 ~/.lambchat/pat（0600）与 ~/.lambchat/sandbox.json（server_url/confirm_policy/data_root 默认）——stdlib fs 实现
#[tauri::command] fn restart_daemon(app: AppHandle) -> Result<(), String>  // stop→start
#[tauri::command] fn daemon_process_status(...) -> String                  // 委托 daemon::status
#[tauri::command] fn open_local_path(path: String) -> Result<(), String>   // 白名单 ~/.lambchat/{workspaces,audit} 前缀校验后 opener 打开
```
- 前端封装 `frontend/src/services/tauri/sandboxShell.ts`：`isShellAvailable()`（isNativeAppRuntime）、`savePairing/restartDaemon/openLocalPath`，非壳环境返回明确错误（调用方降级 UI）

**Steps:**
- [ ] Step 1: 写前端封装的失败测试（`tests` 或 `__tests__` 按仓库惯例：mock @tauri-apps/api/core 的 invoke，断言参数与降级路径）
- [ ] Step 2: RED → 实现 Rust 命令 + 注册 + 前端封装 → GREEN（前端 vitest）
- [ ] Step 3: `cargo build` + Commit `feat(sandbox): 壳内配对/配置/目录命令与前端 invoke 封装`

### Task 4: 托盘菜单

**Files:** Modify `src/lib.rs`（tray-icon feature 已在 T2 加）

**Interfaces:** `TrayIconBuilder`：icon 复用默认；菜单项：显示主窗口 / 打开工作区目录 / 打开审计目录 / 退出（=stop daemon + app exit）。托盘点击恢复窗口。无在线状态轮询（状态在网页 UI，保持简单）。

**Steps:**
- [ ] Step 1: 实现（Rust）→ cargo build → Step 2: dev 冒烟（托盘出现、菜单可用；Linux 需要 appindicator——本机是否有 `libayatana-appindicator3-1` 运行库，缺则装或记录 T8）
- [ ] Step 3: Commit `feat(sandbox): 托盘菜单（工作区/审计/退出）`

### Task 5: 前端配对 UI + 状态轮询

**Files:** Create `frontend/src/services/api/sandbox.ts`（`getSandboxStatus()` → GET /api/sandbox/status）、`frontend/src/hooks/useSandboxStatus.ts`（useTodayUsageCost 模式：10s 轮询 + in-flight 去重 + `sandbox-status-refresh` 事件）；Modify `ProfilePreferencesTab.tsx`

**UI 契约（本地沙箱分区，仅 isNativeAppRuntime() 时渲染）：**
- 状态行：在线圆点（绿/灰）+ `daemon_version` + 进程状态（invoke daemon_process_status）
- 未配对：用户名/密码表单（复用 auth api 的 login → POST /api/auth/pat）→ `savePairing(API_BASE, pat, policy)` → `restartDaemon()` → 触发状态刷新事件
- 已配对：确认策略 SelectRow（all/commands/none 三档 → 经 invoke 写配置 → restartDaemon）、"打开工作区目录"/"打开审计目录"按钮（openLocalPath）、"重启 daemon" 按钮
- 纯 web 环境：分区渲染为"需要桌面端"提示文案（五语）

**Steps:**
- [ ] Step 1: 写失败测试（组件测试 jsdom：mock sandboxShell/api，断言未配对表单提交链路与已配对策略切换调用、web 环境降级文案；hook 纯逻辑提取可测部分）
- [ ] Step 2: RED → 实现 → GREEN（`pnpm test` 定向 + 全量）→ `pnpm run build`
- [ ] Step 3: Commit `feat(frontend): 本地沙箱配对分区与状态轮询`

### Task 6: 会话沙箱选择器

**Files:** Modify `frontend/src/hooks/useAgentOptions.ts`（normalizeAgentOptions 注入 `sandbox` string 型选项：default "cloud"，options cloud/local——**仅当前 agent 是 search agent 或存在 code interpreter 能力时注入**，简化：统一注入，云端沙箱不可用时服务端自然回退既有行为）、`ChatInputSelectors.tsx`（string 型选项已有面板渲染路径？若 sandbox 需要 icon/label_key 则在 locales 补 agentOptions.sandbox.*）

**行为契约：**
- 选择器出现在聊天输入区选项按钮组（与思考档位并列），云端/本地两档
- 本地档时按钮旁挂在线状态点（useSandboxStatus），离线时点击弹提示（五语："本地沙箱离线，命令将执行失败/请先在设置中配对"）但仍允许选择（服务端会报 daemon_offline）
- agent_options.sandbox 随既有链路自动持久化/恢复（session metadata，无需额外代码——已核实 useSessionConfig 恢复 agent_options）

**Steps:**
- [ ] Step 1: 写失败测试（useAgentOptions 纯函数：注入后 default/options 形状；ChatInputSelectors 源码结构断言 sandbox key 与状态点渲染分支）
- [ ] Step 2: RED → 实现 → GREEN
- [ ] Step 3: Commit `feat(frontend): 会话沙箱选择器与在线状态点`

### Task 7: i18n ×5 全量

**Files:** `frontend/src/i18n/locales/{zh,en,ja,ko,ru}.json`

**Keys：** `agentOptions.sandbox.{label,description,options.{cloud,local}}`、`profile.localSandbox.{title,statusOnline,statusOffline,version,processState,pairTitle,pairButton,pairedAs,policy,policyOptions.{all,commands,none},openWorkspaces,openAudit,restartDaemon,needDesktop,pairFailed}`（以 T5/T6 实际用到的为准，实现时同步；五语全部补齐）

**Steps:** 补齐五文件 → `pnpm test`（extract-i18n 一致性 + 既有 i18n 测试）→ Commit `feat(i18n): 本地沙箱五语文案`

### Task 8: 端到端冒烟（dev 链路）

**Steps（控制器或实现者执行，产出 `docs/superpowers/plans/2026-09-05-local-sandbox-m3-smoke.md`）：**
- [ ] 起 mongo/后端（worktree）；`make client-build-daemon`
- [ ] `tauri dev`：壳起 → 设置页配对（m1_smoke）→ daemon 随壳启动在线（status online + daemon_version）
- [ ] 前端选本地沙箱 → 发一条会话（**若本地 DB 无模型配置，降级验证**：提交体带 agent_options.sandbox=local 到达后端——用浏览器 devtools/网络面板或后端日志确认；dispatch 直发一条 exec 验证 daemon 响应）
- [ ] kill -9 daemon 进程 → 壳 3 次内自动重启 → status 回在线
- [ ] 退出壳 → 12ms 级 offline（daemon 被托管 stop，走 offline 通知）
- [ ] 关环境、写记录、Commit `docs(sandbox): M3 端到端冒烟记录`

## Self-Review 记录

- Spec 覆盖：§5 sidecar/externalBin/健康重启/托盘/首次配对=T2/T3/T4/T5；§6 选择器/设置分区=T5/T6；§0 版本行（随壳更新=T2 天然达成，updater artifacts 已开）；网页端无壳引导=T5 降级文案。
- 与 spec 的偏差（裁决）：① 托盘不做在线状态轮询（网页 UI 已有状态灯，托盘保持静态菜单）；② 沙箱选择器统一注入所有 agent（不做 agent 能力过滤，云端档为既有默认行为）；③ agent 文件工具专属 Item 不在本里程碑（现有 ToolPart 通用渲染已可用，列 M4 增强项）。
- 依赖新增：pyinstaller（dev）、tauri-plugin-shell/opener（Rust+前端 JS 绑定 @tauri-apps/plugin-shell 若前端需要——本计划 Rust 托管为主，前端仅 invoke 自定义命令，无需 JS shell 绑定；opener JS 绑定也不需要）。
