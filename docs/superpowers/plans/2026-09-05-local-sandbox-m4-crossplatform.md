# 本地沙箱 M4（三平台 + 自动更新 + 分发收口）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** daemon 三平台一等支持（win/mac/linux）+ 版本管理闭环（self-update + 服务端最低版本拒连）+ M3 递延收口，Linux 全量自测。

**Architecture:** 沿用 Tauri sidecar（业界调研结论：现成壳即正解，Codex/Claude Code 均原生三平台、不 WSL-first）。daemon 侧加平台抽象：Windows 用 **Job Object**（一个机制同时解决超时杀树与父死孤儿）、内嵌 **python-build-standalone** 消灭 python3 环境依赖、文件命令生成器平台分支（cmd 引用替代 shlex）。版本闭环：服务端 min-version 拒连 + CLI `update` 自更新。

**Tech Stack:** ctypes Job Object（Windows，零新依赖）、python-build-standalone（资源随壳分发）、既有 PyInstaller/Tauri 矩阵。

**Spec:** `docs/superpowers/specs/2026-09-01-local-sandbox-design.md` §0 跨平台行/版本管理行、§9 分发；业界调研结论（Codex Windows 沙箱/Seatbelt/Landlock+PDEATHSIG、Claude Code Bun 单文件+Git Bash 依赖痛点、Job Object 权威资料）已并入本计划各任务。

## Global Constraints

- 工作目录：**全程 worktree `/home/yangyang/LambChat/.worktrees/sandbox-m2-client`**。
- **Linux 行为零回归**：所有平台分支以抽象层隔离，Linux 路径 diff 为零（T1 用全量测试锁死）；Windows/macOS 代码路径在 Linux 上以 mock/字符串生成断言单测，真机验证挂 CI（T9）与后续人工——本地无法跑 win/mac 属已知边界，各任务报告如实标注。
- 明确不做（调研背书）：Codex 式 Windows 受限令牌/沙箱用户沙箱（数月级投入）；WSL-first；Nuitka/cargo-dist 迁移；macOS Seatbelt（M5+ 可选）。
- 文案五语；Conventional Commits 中文；服务端改动守 M1 全部约束（ErrorCode/i18n/无 HTTPException）。

## File Structure

```
client/lambchat_sandbox/platform.py     # 新：平台抽象（is_windows/is_macos、shell 引用、job 常量）
client/lambchat_sandbox/executor.py     # 改：Windows Job Object 分支 + POSIX 现状
client/lambchat_sandbox/procsup.py      # 新：父进程存活监视（Windows 替代 PDEATHSIG）
client/lambchat_sandbox/pbs.py          # 新：内嵌解释器管理（解压/shim/PATH）
client/lambchat_sandbox/selfupdate.py   # 新：CLI update（查 release→下载→替换→重启）
client/lambchat_sandbox/cli.py          # 改：update 子命令
client/lambchat_sandbox/__main__.py     # 改：PDEATHSIG 仅 Linux（已如此）+ Windows 挂 procsup
client/scripts/fetch-pbs.py             # 新：构建期下载 python-build-standalone（win/mac）
src/infra/backend/local.py              # 改：文件命令生成平台分支（cmd quote/python/makedirs）
src/kernel/config/base.py               # 改：SANDBOX_MIN_DAEMON_VERSION = "0.1.0"
src/api/routes/sandbox.py               # 改：channel 按 version 拒连（新错误码）
src/kernel/errors.py + scripts/sync_error_locales.py  # 改：DAEMON_VERSION_UNSUPPORTED + 五语
frontend/src/components/profile/LocalSandboxSection.tsx  # 改：配对流重构（无副作用+pat_id 吊销）
frontend/src-tauri/src/daemon.rs        # 改：SIGTERM 处理、stop 走 SIGTERM+宽限、托盘 sys-locale
frontend/src-tauri/capabilities/default.json  # 改：最小化
frontend/src-tauri/Cargo.toml           # 改：Cargo.lock 入库（删 gitignore 行）
.github/workflows/app-release.yml       # 改：恢复 win/mac 矩阵 + 三平台 daemon 步 + PBS 步
tests/client/test_platform.py / test_executor_win.py / test_procsup.py / test_pbs.py / test_selfupdate.py
tests/infra/backend/test_local_backend.py  # 改：Windows 命令生成断言
tests/api/routes/test_sandbox_routes.py   # 改：version 拒连
```

---

### Task 1: 平台抽象层 + Linux 零回归锁

**Files:** Create `client/lambchat_sandbox/platform.py`、`tests/client/test_platform.py`
**Interfaces:** `is_windows()/is_macos()/is_posix()`（可注入 `_sys_platform` 便于测试）、`shell_quote(s, platform)`（posix→shlex.quote；windows→cmd 双引号转义规则：包裹双引号、内部 `"`→`\"`、尾部反斜杠加倍——写明引用的微软文档规则）、`join_cmd(parts, platform)`。
**Steps:** RED（三函数用例：posix quote 照 shlex；windows quote 用 `"a b"`、`he said "hi"`、`trailing\` 用例锁规则）→ 实现 → GREEN → `uv run pytest tests/client -q` 全量（Linux 零回归基线 155+）。Commit `feat(sandbox): 客户端平台抽象层（引用规则/平台判定）`

### Task 2: Windows executor——Job Object + 父进程监视

**Files:** Modify `executor.py`；Create `procsup.py`；Test `test_executor_win.py`、`test_procsup.py`
**要点：**
- executor.execute 平台分支：POSIX 现状（start_new_session+killpg）；Windows（`sys.platform=="win32"` 或 platform.is_windows()）：ctypes 实现 Job Object 样板——`CreateJobObjectW` → `JOB_OBJECT_EXTENDED_LIMIT_INFORMATION` 带 `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` → `SetInformationJobObject` → spawn 后 `AssignProcessToJobObject` → 超时 `TerminateJobObject`。约 60 行 ctypes，注释标注 MS 文档条款。
- procsup.py：`watch_parent(exit_fn, poll_s=2.0)`——线程轮询父 pid 存活（Windows 无 PDEATHSIG；psutil 已是主依赖可用 `psutil.pid_exists`+`os.getppid()` 快照对比），父亡→exit_fn（daemon 优雅退出：post_offline+sys.exit）。__main__ 仅 Windows 挂载。
- 测试（Linux 上）：Job Object ctypes 函数封装为可注入 `_winapi` 模块对象 mock 断言调用序与参数（CreateJobObjectW→SetInformationJobObject(KILL_ON_JOB_CLOSE)→AssignProcessToJobObject(child)→超时 TerminateJobObject）；procsup 用真实线程+假父（spawn 短命子进程当"父"）验证父亡回调触发；executor Linux 路径全量回归。
**Commit** `feat(sandbox): Windows 执行器 Job Object 与父进程监视`

### Task 3: 文件命令生成器平台分支（local.py）

**Files:** Modify `src/infra/backend/local.py`；Test `tests/infra/backend/test_local_backend.py` 追加
**要点：** 服务端为 Windows daemon 生成命令时——`python3 -c` → `"{内嵌解释器}python.exe" -c`？**决策：daemon 侧 PATH 已含内嵌 python3.exe shim（T4），服务端命令生成保持 `python3` 不变**——唯一必须改的：`mkdir -p` 前缀（POSIX）→ 平台分支（服务端怎么知道 daemon 平台？**registry 已存 node_id（hostname）——不够**。方案：daemon_version 上报时带 platform（registry value 扩展为 `node|version|platform`，向后兼容解析），服务端按 platform 选 `mkdir -p` 或省略（Windows 分支把 mkdir 并进 python 脚本 os.makedirs）与 shell 引用（shlex vs cmd——命令里的路径引用由 platform.shell_quote 逻辑服务端复刻：引用逻辑抽到服务端小函数与 client/platform.py 同规则，双侧单测锁一致）。
**验收：** Linux daemon 路径命令串逐字节不变（既有测试全绿）；Windows platform 注册后生成的命令串无 POSIX 语法（新增断言用例：mkdir 不出现/引用为 cmd 风格）。
**Commit** `feat(sandbox): 文件命令生成平台分支与 daemon 平台上报`

### Task 4: 内嵌 python-build-standalone

**Files:** Create `client/scripts/fetch-pbs.py`（构建期下载指定版本 PBS：win x86_64-pc-windows-msvc / mac arm64+x64 的 install_only tar.gz 到 src-tauri/resources/python/）、`client/lambchat_sandbox/pbs.py`；Modify `tauri.conf.json`（bundle.resources）、`client/lambchat_sandbox/daemon.py`（executor env PATH 前置）
**要点：** daemon 启动时 `pbs.ensure_runtime()`：若 `~/.lambchat/python/<tag>/` 缺失则从壳 resources（或配置的 URL）解压；建 `~/.lambchat/bin/python3(.exe)` shim（复制 python.exe）+ 把该目录前置进 executor 子进程 PATH。Linux 同样启用（统一行为、可全测）——Linux PBS 也存在（install_only tar.gz），体积换一致性，配置项 `embedded_python: true|false`（默认 true，false 走系统 PATH）。
**测试（Linux 全测）：** ensure_runtime 解压幂等、shim 可执行且 `python3 --version` 输出、PATH 前置后 executor 的 `python3 -c` 命中内嵌（用 `python3 -c "import sys;print(sys.executable)"` 断言路径）、embedded_python=false 回退系统。
**Commit** `feat(sandbox): 内嵌 python-build-standalone 运行时`

### Task 5: 服务端最低版本拒连

**Files:** Modify `base.py`（`SANDBOX_MIN_DAEMON_VERSION: str = "0.1.0"` + .env.example）、`sandbox.py`（channel 端点：query version 与 min 比较语义化（tuple(int) 比较，容错非数字段→按最低处理）→ 低于则拒绝连接返回新错误码）、`errors.py`+sync 脚本（`DAEMON_VERSION_UNSUPPORTED = ("daemon_version_unsupported", 426, "Daemon version {{version}} is below minimum {{min}}; please update")` 五语）
**测试：** 高于/等于放行、低于 426 拒连（SSE 端点错误返回形态照 channel 现有错误路径）、坏版本字符串容错。
**Commit** `feat(sandbox): 服务端最低 daemon 版本拒连`

### Task 6: CLI self-update

**Files:** Create `selfupdate.py`、Modify `cli.py`（`update` 子命令）；Test `test_selfupdate.py`
**要点：** `update`：GET `https://api.github.com/repos/Yanyutin753/LambChat/releases/latest`（可配置 repo）→ 找平台资产（lambchat-daemon-<triple> 或壳安装包）→ 比版本（高于当前才继续）→ 下载到临时 → **替换自体**：onefile 二进制在跑时不能直接覆盖自身——写新文件到旁边+改名交换（Linux `os.rename` 原子；Windows 先旧改名再新改名）→ 打印"重启后生效"。**壳形态的更新由 Tauri updater 负责（不归此命令）**，update 只服务 CLI 直跑场景。网络失败/无新版本/校验（sha256 资产 digest 若有）各路径明确输出。
**测试：** mock httpx：有新版本→下载替换调用序（假文件系统 tmp_path 真实替换）；已是最新→提示不动作；请求失败→错误码。
**Commit** `feat(sandbox): CLI self-update`

### Task 7: 配对流重构（PAT 精准吊销 + 无副作用登录）

**Files:** Modify `LocalSandboxSection.tsx`（登录改直连 fetch `/api/auth/login` 不经 authApi（不 setTokens/不派发事件）；createPat 后把 `pat_id` 一并存入壳侧——sandbox.json 加 `pat_id` 字段（Rust save_pairing 加可选参数，Python config 忽略未知字段天然兼容）；重铸前若存 pat_id → 先 DELETE 旧 PAT 再创建）；Rust `daemon.rs save_pairing` 加 `pat_id` 参数落盘；策略切换不再重铸 PAT（仅写配置+restart）。
**测试：** 前端链路（mock fetch：断言无 auth:login 事件、旧 pat_id 吊销调用先于创建）；Rust cargo test（save_pairing 含 pat_id 落盘）。
**Commit** `feat(sandbox): 配对流重构——无副作用登录与 PAT 精准吊销`

### Task 8: 壳侧收口（M3 递延）

**Files:** Modify `daemon.rs`（SIGTERM 信号处理器跑 stop；stop 改 SIGTERM+3s 宽限再 SIGKILL，daemon 侧已有 SIGTERM 优雅退出→post_offline 生效）、`tray.rs`（sys-locale 选五语文案表）、`capabilities/default.json`（移除 shell:default/shell:allow-execute/opener:default——核实 Rust 侧确不依赖）、`.gitignore`（删 Cargo.lock 行，提交 lockfile）、`useSandboxStatus` 消费方门控（RunModePopover 仅 open 时轮询）
**验证：** cargo build/test + 前端全量 + tauri dev 实测：关窗/TERM 壳 → daemon 收 SIGTERM → **status ≤3s offline（post_offline 生效，对照 M3 记录的 54s TTL）**。
**Commit** `feat(sandbox): 壳侧收口——SIGTERM 优雅停机/托盘五语/权限最小化`

### Task 9: CI 三平台矩阵恢复

**Files:** Modify `.github/workflows/app-release.yml`
**要点：** 恢复 win/mac include 条目（取消注释）；每平台 daemon 步：win（windows runner `uv run pyinstaller`→`lambchat-daemon-x86_64-pc-windows-msvc.exe`）、mac arm64（macos-14 runner→`aarch64-apple-darwin`）；mac universal 先单 arm64（Tauri target 相应改 `aarch64-apple-darwin`，universal+lipo 列 M5）；PBS fetch 步（T4 脚本，win/mac 下载对应 PBS 到 resources）；保持 Linux 现状。
**验证：** YAML 解析 + 结构断言（三平台各含 daemon 步）+ actionlint（若无则 python yaml + 自写断言）；真实 tag 端到端留首次发版。
**Commit** `ci(release): 三平台 daemon 构建与 PBS 资源`

### Task 10: Linux 全量自测 + 记录

**Steps：** `make lint && make typecheck && uv run pytest tests -q`（全量）+ `cd frontend && pnpm test && pnpm run build` + tauri dev 实测链（配对→sidecar 在线→kill -9 自愈→SIGTERM 壳停机 ≤3s offline→self-update "已是最新"路径→min-version 拒连用旧版本号冒烟）→ 写 `docs/superpowers/plans/2026-09-06-local-sandbox-m4-smoke.md`（win/mac E2E 明确标注留 CI/人工）→ Commit。

## Self-Review 记录

- 覆盖：调研"必做清单"6 项=T1-T4/T9/T6；用户版本管理要求=T5/T6；M3 终审/递延收口=T7/T8；spec §9 签名证书仍开放（用户决策，不阻塞）。
- 已裁决偏差：mac 先 arm64 单架构（universal M5）；CLI self-update 只管 CLI 形态（壳归 Tauri updater）；Linux 也启用内嵌解释器（统一可测，配置可关）。
- 本地边界：win/mac 真机行为=mock 单测+CI 矩阵+人工后验（T10 记录），与用户"自测"要求的差距如实呈现。
