# LambChat 客户端开发规范

> 定位：与 `DESIGN.md` / `PRODUCT.md` 同级的领域专项规范——`AGENTS.md` 是全仓唯一开发规范主干，本文件只做客户端领域的细化，不重复其通用规则。
>
> 参考框架：[elsewhencode/project-guidelines](https://github.com/elsewhencode/project-guidelines)（29k+ stars，多语言版本），按其十大章节骨架结合本仓库现状裁剪；移动端专项补充参考 [futurice/android-best-practices](https://github.com/futurice/android-best-practices)。

## 0. 范围与原则

**范围**：Tauri 桌面端（`frontend/src-tauri/`）、Capacitor 移动端（`frontend/android/`、`frontend/ios/App/`）、本地沙箱 daemon（`client/lambchat_sandbox/`），以及三者共用的发布链路（`app-release.yml`、`desktop-updater-publish.yml`）。

**原则：**

- 三端共享同一 WebView 前端（`frontend/src/`），UI/交互规范以 `DESIGN.md` 为准，本文件只管「壳」与平台层。
- 平台差异收敛：能力缺口优先用 Tauri command / Capacitor plugin 补，禁止在 WebView 层散落 `navigator.userAgent` 嗅探分支；确需平台判断的，收敛到统一工具函数并在此登记。
- 面向用户的原生 UI 文案（托盘菜单、通知、原生对话框）与前端同责：同步更新 zh / en / ja / ko / ru 五个 locale（参照 `tray.rs` 的 sys-locale 机制）。
- 分支模型、提交规范、发版节奏、hotfix 流程一律以 `AGENTS.md` 为准，本文件不重述。

## 1. Git（对应 project-guidelines §1）

- 通用规则遵循 `AGENTS.md`（feat/* → develop，Conventional Commits + 中文摘要）。
- **规矩：涉及 daemon 协议的改动（`client/lambchat_sandbox/` 的 `transport.py` / `frames.py` / `auth.py`），PR 描述必须注明是「向后兼容」还是「需壳+daemon 同版发版」**——daemon 自更新按版本比较拉新，协议破坏性变更必须跨至少一个版本双向兼容。
- 原生工程目录（`frontend/android/`、`frontend/ios/App/`）的改动单独成 commit，不带 WebView 代码改动，便于回溯 Xcode/Gradle 层回归。
- `frontend/src-tauri/binaries/`、`resources/python/` 产物不进 git（已有 .gitignore 覆盖），禁止「顺手提交一个能跑的 sidecar」。

## 2. 文档（§2）

- 每个**新增** Tauri command 在 PR 描述列出：名称、入参出参、副作用、所需 capability；`daemon.rs` 现有 8 个 command 作为基线。
- VitePress `docs/` 增设「客户端开发」章节（现状缺失）：本地跑桌面壳、`mobile:sync` 流程、daemon 调试、日志位置、常见打包问题排查。
- 打包链路的行为变更（签名、冒烟门禁、latest.json 逻辑）同步更新 `AGENTS.md` 发版流程一节——两处口径必须一致。

## 3. 环境（§3）

- Node 版本由 `frontend/package.json` engines + pnpm lockfile 锁定；Rust 工具链用 `frontend/src-tauri/rust-toolchain.toml` 锁定（**待补**，见 §11）。
- PBS runtime 与 PyInstaller 版本必须 pin 精确版本，禁止 `latest`；升级单独 PR。
- 本地开发起点：`make client-fetch-pbs` + `make client-build-daemon`；建议补 `make dev-desktop` 一键拉起桌面开发壳（§11）。

## 4. 依赖（§4）

- **daemon 保持 stdlib + httpx 的极简依赖面**，新增依赖必须在 PR 说明理由（PyInstaller onefile 体积与冷启动对此敏感）。
- npm 侧 `@tauri-apps/*` 与 Cargo 侧 `tauri` 保持同 major.minor（`Cargo.toml` 注释已要求，升级时双重检查）。
- tauri / capacitor 主版本升级必须单独 PR，且六端构建 + 冒烟门禁全绿才算过。

## 5. 代码风格与静态检查（§7）

现状矩阵：

| 层 | 工具 | 现状 |
|----|------|------|
| TS / React | ESLint 9 flat + strict tsconfig + prettier（pre-commit） | ✅ 已有 |
| Rust（src-tauri） | rustfmt + clippy | ❌ 无配置、无 CI 步骤（**待补**） |
| daemon Python | ruff + ruff-format（pre-commit） | ✅ 已有 |

**规矩：**

- Rust 侧补 `Cargo.toml [lints]`（至少 `clippy::unwrap_used`、`clippy::expect_used` 在 Tauri command 路径禁用）+ `lint.yml` 增加 `cargo fmt --check` / `cargo clippy -D warnings` 步骤。
- 仓库已有前端 1500 行文件检查，但 Rust 不在覆盖面：`daemon.rs` 已 1300+ 行，**新增 Tauri command 一律新建模块文件**（如 `commands/`），不再往 `daemon.rs` 堆；单文件超 800 行就该拆。

## 6. 结构与命名（§6）

| 位置 | 职责 | 约束 |
|------|------|------|
| `frontend/src-tauri/src/main.rs` | 薄入口 | 不写逻辑 |
| `frontend/src-tauri/src/lib.rs` | 插件注册、setup、退出钩子 | 生命周期类改动必须有 `#[cfg(test)]` 单测 |
| `frontend/src-tauri/src/tray.rs` | 托盘与本地化 | 文案五语齐全 |
| `frontend/src-tauri/src/daemon.rs` | sidecar 生命周期（现有） | 只出不进，新命令进 `commands/` |
| `frontend/android/`、`frontend/ios/App/` | 原生工程 | 只放壳与配置，禁止塞业务逻辑 |
| `client/lambchat_sandbox/` | daemon 本体 | 协议层（frames/transport/auth）改动走 §1 规矩 |

命名沿用现状：Tauri command 用 snake_case 并带领域前缀（`daemon_*` / `read_*`）；Rust 模块名单数名词。

## 7. 桌面端（Tauri）专项

- **安全**：`capabilities/default.json` 最小权限，新 command 显式声明所需权限；CSP 当前为 `null`，属已知债务，收紧计划登记 §11；签名/更新密钥只进 CI secrets，代码与文档不落明文。
- **macOS 特例**：ad-hoc 签名（`signingIdentity: "-"`）+ `hardenedRuntime: false` 是 PBS sidecar 内嵌 dylib 的既定兼容决策，改动此项必须附真机验证结论，否则 CI 签名校验门禁与 Gatekeeper 都可能翻车。
- **sidecar 生命周期契约**：退避重启（上限 3 次、稳定 300s 重置计数）、`kill(pid,0)` 存活探测、SIGTERM 优雅退出、`RunEvent::Exit` 兜底回收——**凡动 `daemon.rs` 或 daemon 进程管理（`procsup.py`），合并前必须跑 `uv run python scripts/e2e_local_sandbox.py` 全绿**（AGENTS.md 硬性门禁）。
- **日志**：统一写 `~/.lambchat/logs/desktop.log`，禁止另起路径；日志里不得出现 token / pairing 凭据明文。

## 8. 移动端（Capacitor）专项

- **流程**：改 WebView 代码后 `pnpm mobile:sync` 重新同步；`android/`、`ios/App/` 的 diff 必须人工过目后再提交，防止 sync 静默改坏原生配置。
- **版本**：`versionCode` = 版本去点数字（2.10.1 → 2101），`versionName` 与六文件版本一致；禁止手改 `build.gradle` / `project.pbxproj` 版本号绕过统一 bump。
- **安全红线**：`allowMixedContent: false` 不动摇，API 一律 https；敏感数据不进 WebView localStorage，走原生侧或后端会话。
- **发布产物现状**：Android 出签名 APK（密钥在 CI secrets，降级 debug APK 需在 Release notes 标注）；iOS 当前为 unsigned xcarchive——签名链路上线前按 §11 推进。

## 9. 版本与发布（§ AGENTS.md 发版流程的客户端细化）

- 六文件 bump 规则以 `AGENTS.md` 为准；`versionCode`（第七处）随 `versionName` 联动。
- **cargo `Cargo.toml` crate 版本当前已漂移（2.8.6 vs `tauri.conf.json` 2.10.1）且 preflight 不校验**——二选一，团队拍板：纳入 preflight 一并 bump（推荐），或在 `Cargo.toml` 注释明确「crate 版本不参与发版」并写明理由。悬空不管是最差选项。
- 建议 bump 脚本化（`scripts/bump_version.py`：一次改齐全部版本文件 + 校验 versionCode 规则），替代手工六处编辑；出 tag 的 preflight 继续兜底。
- 发版完成判据不变：latest.json 五个桌面平台条目齐全（含 `darwin-x86_64`）+ mac/windows 真机抽检通过。

## 10. 测试（§5 + §10）

| 层 | 现状 | 要求 |
|----|------|------|
| TS / React | vitest（CI 有） | 沿用 AGENTS.md TDD 流程 |
| Rust | 仅 `lib.rs` 少量单测，CI 无 `cargo test` | `daemon.rs` / `tray.rs` 改动补单测；`lint.yml` 补快速 `cargo test` |
| daemon 链路 | `e2e_local_sandbox.py`（硬性门禁） | 涉及沙箱链路必跑；发版前加 `--stress` |
| 打包产物 | CI 冒烟门禁（mac/Linux/Windows 三式） | 不豁免；新平台/新包型先补冒烟再合 |

## 11. 落地清单（本规范生效后的补课项）

| 优先级 | 事项 | 对应章节 |
|--------|------|----------|
| P0 | Rust fmt/clippy 配置 + CI 步骤 | §5 |
| P0 | `Cargo.toml` 版本口径拍板（纳入 preflight 或显式豁免） | §9 |
| P0 | 版本 bump 脚本化 | §9 |
| P1 | VitePress「客户端开发」章节 | §2 |
| P1 | `make dev-desktop` 一键桌面开发壳 + `rust-toolchain.toml` | §3 |
| P1 | `lint.yml` 增加 `cargo test` | §10 |
| P2 | CSP 收紧方案 | §7 |
| P2 | iOS 签名链路 | §8 |
