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

- **daemon 保持 stdlib + httpx 的极简依赖面**，新增依赖必须在 PR 说明理由（PyInstaller onefile 体积与冷启动对此敏感）。既有例外：computer-use 的 `cua` 依赖组（`uv sync --group cua`，平台标记互斥）——macOS atomacos（带 PyObjC+pyautogui）、Windows pywinauto+pyautogui、Linux pyautogui+python-xlib（AT-SPI 走系统包 python3-pyatspi）；未同步该组的构建里 cua_* op 报 `unsupported_platform`，其余链路不受影响。
- CUA 必须显式选择在线机器；代码沙箱可为本地或云端，桌面选机与代码沙箱平台独立。工具参数不能覆盖会话选机，未选择、离线或审批后改机均拒绝，不回退到账户默认机器。审批绑定机器和具体操作，按该机器确认策略执行。观察索引仅在当前会话有效。
- 远程服务器地址必须使用 HTTPS，HTTP 仅允许回环开发地址。PAT 绑定签发服务器 origin，改连服务器不复用旧凭据，未绑定的旧凭据须重新配对；服务器反向代理子路径仍保留。凭据文件原子写入，并在写入内容前设置仅本用户可访问的权限。
- 上述传输与账户隔离不等同于服务器失陷后的端到端控制隔离：当前电脑指令仍由服务端 Agent 生成。可信设备执行与端到端配对方案须独立实现、验证后才能声明服务器无控制权。
- CUA 截图仅允许已确认焦点的前台窗口有效区域，密码字段不读取；截图以会话所有者鉴权读取，禁止匿名、共享和签名直链，删除会话时回收。截图会发送给当前模型，窗口内通知或浮层仍可能入镜。新版回传必须携带机器身份，旧 daemon 的流式操作需同步更新；CUA 要求 daemon 2.14.4 或更新版本。
- CUA 截图编码依赖三平台显式安装的 Pillow。Linux 打包机还需 `python3-pyatspi`、`python3-gi` 和 `gir1.2-atspi-2.0`，PyInstaller 从系统 Python 路径收集 AT-SPI 与 GI；构建 Python 的 minor 版本必须与系统 GI 扩展一致。Linux X11 的窗口激活和前台检测需 `wmctrl` / `xdotool`。Windows 必须有已登录的交互桌面；SSH 服务会话不能截取登录界面。Wayland 当前支持无障碍元素读写、点击和元素滚动，截图及全局键鼠仍受系统限制，不能把成功的元素操作视为全功能验证。
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

- **Windows 安装升级**：NSIS 安装包检测到旧安装后直接显示升级进度并沿用原目录，首次安装保留完整向导；普通、静默、应用内更新与同版本重装统一在复制文件前按安装目录停止旧主程序/daemon，再以 `/S /UPDATE` 运行旧卸载器；不删除聊天、登录和工作区数据。64 位系统使用原生 PowerShell，停止或卸载失败必须中止。`scripts/test_windows_installer_hooks.ps1` 用真实 NSIS 安装/卸载夹具验证该流程，PR CI 与 Windows 出包均执行；Tauri CLI 或 NSIS 升级时同步验证 Modern UI 初始化钩子与卸载分流。

- **macOS 标题栏对齐**：`src/titlebar.rs` 按 AppKit 按钮实际高度对齐 36px WebView 顶栏（含 1px 底边框，内容中心为距顶端 17.5px）；使用原生通知在缩放、退出全屏、切换显示器、恢复窗口和重新聚焦后校正，不替换 Tauri 的窗口 delegate。不要再配置 `trafficLightPosition`，否则 Tao/Wry 会在布局时覆盖原生校正。修改后运行 `cd frontend/src-tauri && cargo run --example verify_titlebar_alignment`（真实原生控件与通知处理器冒烟；需要 macOS 及客户端构建资源），并打包检查实际缩放与全屏往返。
- **安全**：`capabilities/default.json` 最小权限，新 command 显式声明所需权限；CSP 当前为 `null`，属已知债务，收紧计划登记 §11；签名/更新密钥只进 CI secrets，代码与文档不落明文。
- **macOS 特例**：ad-hoc 签名（`signingIdentity: "-"`）+ `hardenedRuntime: false` 是 PBS sidecar 内嵌 dylib 的既定兼容决策，改动此项必须附真机验证结论，否则 CI 签名校验门禁与 Gatekeeper 都可能翻车。
- **sidecar 生命周期契约**：退避重启（上限 3 次、稳定 300s 重置计数）、`kill(pid,0)` 存活探测、SIGTERM 优雅退出、`RunEvent::Exit` 兜底回收——**凡动 `daemon.rs` 或 daemon 进程管理（`procsup.py`），合并前必须跑 `uv run python scripts/e2e_local_sandbox.py` 全绿**（AGENTS.md 硬性门禁）。
- **日志**：统一写 `~/.lambchat/logs/desktop.log`，禁止另起路径；日志里不得出现 token / pairing 凭据明文。

## 8. 移动端（Capacitor）专项

- **应用图标**：`frontend/resources/mobile-icon.png` 是 512×512 RGBA 原图，底板纯白且不透明；由 `pnpm brand:assets` 同步 Android launcher、`resources/icon.png` 与 1024×1024 RGB iOS AppIcon（无 alpha 通道），`pnpm brand:assets:check` 校验一致性。系统负责移动端外轮廓裁切，不在原图画圆角。桌面端独立使用 `resources/native-icon.png`，Web 图标继续沿用现有素材。
- **流程**：改 WebView 代码后 `pnpm mobile:sync` 重新同步；`android/`、`ios/App/` 的 diff 必须人工过目后再提交，防止 sync 静默改坏原生配置。
- **版本**：`versionCode` = 版本去点数字（2.10.1 → 2101），`versionName` 与六文件版本一致；禁止手改 `build.gradle` / `project.pbxproj` 版本号绕过统一 bump。
- **安全红线**：`allowMixedContent: false` 不动摇，API 一律 https；敏感数据不进 WebView localStorage，走原生侧或后端会话。
- **发布产物现状**：Android 出签名 APK（密钥在 CI secrets，降级 debug APK 需在 Release notes 标注）；iOS 当前为 unsigned xcarchive——签名链路上线前按 §11 推进。

## 9. 版本与发布（§ AGENTS.md 发版流程的客户端细化）

- 六文件 bump 规则以 `AGENTS.md` 为准；`versionCode`（第七处）随 `versionName` 联动。
- **cargo `Cargo.toml` crate 版本当前已漂移（2.8.6 vs `tauri.conf.json` 2.10.1）且 preflight 不校验**——二选一，团队拍板：纳入 preflight 一并 bump（推荐），或在 `Cargo.toml` 注释明确「crate 版本不参与发版」并写明理由。悬空不管是最差选项。
- 建议 bump 脚本化（`scripts/bump_version.py`：一次改齐全部版本文件 + 校验 versionCode 规则），替代手工六处编辑；出 tag 的 preflight 继续兜底。
- 发版完成判据不变：latest.json 三个桌面平台条目齐全（Windows x64、macOS Apple Silicon / Intel）（含 `darwin-x86_64`）+ mac/windows 真机抽检通过。

### 模型调用与跨端一致性

- Web、Tauri（macOS / Windows / Linux）、Capacitor（Android / iOS）共享助手目录与五语文案；轻量助手保留 `quick` 标识，已有会话和助手偏好继续有效。
- 所有已注册模型协议共用瞬态错误分类：连接故障、超时、408 / 409 / 429 / 5xx 按 `LLM_MAX_RETRIES` 和 `LLM_RETRY_DELAY` 重试。主模型失败后使用模型配置或全局配置中的 fallback；401 / 403 直接切备用模型，不重试相同凭据。
- 轻量助手的直接调用也使用共享重试 / fallback；直接调用已经交付流式内容后不重放请求，取消立即传播。备用模型失败后终止，不循环切换。
- 桌面烘焙期间自动更新主端点回退到最近已发布稳定版清单；手动检查直接依据返回的版本结果反馈，检查、下载和待安装状态不互相覆盖。

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
