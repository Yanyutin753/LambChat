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

- 通用规则遵循 `AGENTS.md`（feat/\* → develop，Conventional Commits + 中文摘要）。
- **规矩：涉及 daemon 协议的改动（`client/lambchat_sandbox/` 的 `transport.py` / `frames.py` / `auth.py`），PR 描述必须注明是「向后兼容」还是「需壳+daemon 同版发版」**——daemon 自更新按版本比较拉新，协议破坏性变更必须跨至少一个版本双向兼容。
- 原生工程目录（`frontend/android/`、`frontend/ios/App/`）的改动单独成 commit，不带 WebView 代码改动，便于回溯 Xcode/Gradle 层回归。
- `frontend/src-tauri/binaries/`、`resources/python/` 产物不进 git（已有 .gitignore 覆盖），禁止「顺手提交一个能跑的 sidecar」。

Dev Release 规则以 `AGENTS.md`「Dev Release：下一版本预发布」为准。默认正式版通道；用户在偏好或下载页主动选择测试版后，可获取已完成 CI、原生打包和签名校验的 dev 更新。选择仅保存在当前设备；下载或安装期间禁止切换。CI 将完整 tag 注入前端与桌面更新比较，平台安装版本仍使用核心版本和构建号。旧 dev.2 及更早版本需手动安装一次支持通道的新包。测试通道允许晋升同核心正式版；切回正式通道不自动降级。iOS 沿用发布页下载，不承诺自动安装。

## 2. 文档（§2）

- 每个**新增** Tauri command 在 PR 描述列出：名称、入参出参、副作用、所需 capability；`daemon.rs` 现有 8 个 command 作为基线。
- VitePress `docs/` 增设「客户端开发」章节（现状缺失）：本地跑桌面壳、`mobile:sync` 流程、daemon 调试、日志位置、常见打包问题排查。
- 打包链路的行为变更（签名、冒烟门禁、latest.json 逻辑）同步更新 `AGENTS.md` 发版流程一节——两处口径必须一致。

## 3. 环境（§3）

- Node 版本由 `frontend/package.json` engines + pnpm lockfile 锁定；Rust 工具链用 `frontend/src-tauri/rust-toolchain.toml` 锁定（**待补**，见 §11）。
- PBS runtime 与 PyInstaller 版本必须 pin 精确版本，禁止 `latest`；升级单独 PR。
- 本地开发起点：`make client-fetch-pbs` + `make client-build-daemon`；建议补 `make dev-desktop` 一键拉起桌面开发壳（§11）。

## 4. 依赖（§4）

- **daemon 保持 stdlib + httpx 的极简依赖面**，新增依赖必须在 PR 说明理由（PyInstaller onefile 体积与冷启动对此敏感）。既有例外：computer-use 的 `cua` 依赖组（`uv sync --group cua`，平台标记互斥）——macOS atomacos（带 PyObjC+pyautogui）、Windows pywinauto+pyautogui、Linux pyautogui+python-xlib（AT-SPI 走系统包 python3-pyatspi）；未同步该组的构建里 cua\_\* op 报 `unsupported_platform`，其余链路不受影响。
- CUA 必须显式选择在线机器；代码沙箱可为本地或云端，桌面选机与代码沙箱平台独立。工具参数不能覆盖会话选机，未选择、离线或审批后改机均拒绝，不回退到账户默认机器。审批绑定机器和具体操作，按该机器确认策略执行。观察索引仅在当前会话有效。
- 远程服务器地址必须使用 HTTPS，HTTP 仅允许回环开发地址。PAT 绑定签发服务器 origin，改连服务器不复用旧凭据，未绑定的旧凭据须重新配对；服务器反向代理子路径仍保留。凭据文件原子写入，并在写入内容前设置仅本用户可访问的权限。
- 上述传输与账户隔离不等同于服务器失陷后的端到端控制隔离：当前电脑指令仍由服务端 Agent 生成。可信设备执行与端到端配对方案须独立实现、验证后才能声明服务器无控制权。
- daemon 的有界 call_id 去重同时记录请求终态：结果已受理（含流式结果）或服务端明确拒绝过期回传后，重复帧仅记审计并跳过 HTTP；结果尚未确认的重复帧仍补发 ACK，避免旧终态调用阻塞后续请求。
- CUA 截图仅允许已确认焦点的前台窗口有效区域，密码字段不读取；截图以会话所有者鉴权读取，禁止匿名、共享和签名直链，删除会话时回收。截图会发送给当前模型，窗口内通知或浮层仍可能入镜。新版回传必须携带机器身份，旧 daemon 的流式操作需同步更新；CUA 要求 daemon 2.14.4 或更新版本。
- CUA 截图编码依赖三平台显式安装的 Pillow。Linux 打包机还需 `python3-pyatspi`、`python3-gi` 和 `gir1.2-atspi-2.0`，PyInstaller 从系统 Python 路径收集 AT-SPI 与 GI；构建 Python 的 minor 版本必须与系统 GI 扩展一致。Linux X11 的窗口激活和前台检测需 `wmctrl` / `xdotool`；当 AT-SPI 文本写入不生效时，键盘输入使用 X11 Unicode keysym，临时使用空闲非修饰键码并恢复原映射（不覆盖剪贴板、不合成 Shift 切换输入法）。Windows 必须有已登录的交互桌面；SSH 服务会话不能截取登录界面。Wayland 当前支持无障碍元素读写、点击和元素滚动，截图及全局键鼠仍受系统限制，不能把成功的元素操作视为全功能验证。
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

命名沿用现状：Tauri command 用 snake*case 并带领域前缀（`daemon*\_`/`read\_\_`）；Rust 模块名单数名词。

## 7. 桌面端（Tauri）专项

- **macOS 应用下限**：打包最低系统为 **macOS 11.0**，共享前端另需 **系统 WebKit / Safari 16.4+**。Big Sur 与 Monterey 用户须先升级系统 Safari/WebKit；原生通知模块对 10.13 的兼容处理不代表整个应用支持 10.13。Safari 16.4 支持的系统见 [Apple 发布说明](https://developer.apple.com/documentation/safari-release-notes/safari-16_4-release-notes)。
- **Intel macOS 构建依赖**：Intel macOS 的 Python 依赖只支持 3.12/3.13；原生构建固定使用 3.12。上游 ONNX Runtime 最新支持该平台的 wheel 为 1.23.2，其他兼容平台继续使用较新版本；uv 解析须验证 Intel 平台二进制包可安装性。

- **原生通知**：桌面入口集中在 `src/commands/notification.rs`。macOS 弱链接 `UserNotifications` 并在运行时检查类可用性，通知模块保留 10.13 的运行时兼容处理（应用整体下限见本节说明）；可用时通过常驻 `UNUserNotificationCenter` 代理保存内部路由和账户归属，旧 macOS 与 Linux 保留 notification 插件发送。Windows 在 `windows_notification.rs` 使用应用 AUMID 发送，并保留通知及激活回调，支持横幅消失后的通知中心点击。Android 点击沿用 Capacitor。支持点击的平台均由前端 `appNotificationService` 校验当前账户与内部路由，再导航并显示桌面主窗口；不支持进程关闭后的冷启动点击。原生发送 API 成功仅说明系统受理，不能代替目标设备上实际送达与点击的观察证据。

- **Windows 安装升级**：NSIS 安装包检测到旧安装后直接显示升级进度并沿用原目录，首次安装保留完整向导；普通、静默、应用内更新与同版本重装统一在复制文件前按安装目录停止旧主程序/daemon，再以 `/S /UPDATE` 运行旧卸载器；不删除聊天、登录和工作区数据。64 位系统使用原生 PowerShell，停止或卸载失败必须中止。`scripts/test_windows_installer_hooks.ps1` 用真实 NSIS 安装/卸载夹具验证该流程，PR CI 与 Windows 出包均执行；Tauri CLI 或 NSIS 升级时同步验证 Modern UI 初始化钩子与卸载分流。
- **更新签名版本绑定**：平台核心版本保留数字版本；最终 Windows NSIS 与双架构 macOS 更新归档必须由 Tauri CLI `signer sign --app-version` 绑定完整 Release 版本（含 `-dev.N`）。发布前使用真实 `tauri-plugin-updater` 校验文件、公钥与声明版本，并在隔离 runner 验证从稳定版及前一测试版的原生安装/替换；清单生成器拒绝签名版本不一致、缺失或平台不齐。不得关闭版本校验或将 dev 清单降为核心版本规避问题。

- **Windows 安装回归**：先由原生更新器校验候选安装包，再提取 NSIS 内主程序作为安装后哈希基准。Tauri 会把包内程序的安装类型标记改为 NSIS，不能与便携版或恢复后的构建目录 EXE 直接比较。尚未发布就绪清单的 tag 可从受保护的 main 工作流重试；产品构建和签名清单仍绑定原 tag 源提交，验证脚本绑定本次工作流提交，不覆盖 tag。

- **macOS 标题栏对齐**：`src/titlebar.rs` 按 AppKit 按钮实际高度对齐 36px WebView 顶栏（含 1px 底边框，内容中心为距顶端 17.5px）；使用原生通知在缩放、退出全屏、切换显示器、恢复窗口和重新聚焦后校正，不替换 Tauri 的窗口 delegate。不要再配置 `trafficLightPosition`，否则 Tao/Wry 会在布局时覆盖原生校正。修改后运行 `cd frontend/src-tauri && cargo run --example verify_titlebar_alignment`（真实原生控件与通知处理器冒烟；需要 macOS 及客户端构建资源），并打包检查实际缩放与全屏往返。
- **安全**：`capabilities/default.json` 最小权限，新 command 显式声明所需权限；CSP 由 `tauri.conf.json` 配置并由 Tauri 在打包时注入 hash / nonce。CodeMirror 预览与编辑入口通过 `codeMirrorCspNonce` 复用启动样式的 DOM `nonce` 属性，授权动态样式；不可用放宽 CSP 替代 nonce 传递。签名/更新密钥只进 CI secrets，代码与文档不落明文。
- **macOS 特例**：ad-hoc 签名（`signingIdentity: "-"`）+ `hardenedRuntime: false` 是 PBS sidecar 内嵌 dylib 的既定兼容决策，改动此项必须附真机验证结论，否则 CI 签名校验门禁与 Gatekeeper 都可能翻车。
- **sidecar 生命周期契约**：退避重启（上限 3 次、稳定 300s 重置计数）、`kill(pid,0)` 存活探测、SIGTERM 优雅退出、`RunEvent::Exit` 兜底回收——**凡动 `daemon.rs` 或 daemon 进程管理（`procsup.py`），合并前必须跑 `uv run python scripts/e2e_local_sandbox.py` 全绿**（AGENTS.md 硬性门禁）。
- **升级保留数据**：升级或同版本重装不得递归删除 app data / WebView 数据目录；登录、偏好和窗口状态随版本保留。前端资源通过构建产物文件名更新，禁止为刷新资源而清空持久化数据。
- **日志**：统一写 `~/.lambchat/logs/desktop.log`，禁止另起路径；日志里不得出现 token / pairing 凭据明文。
- **Windows 凭证权限**：使用进程 token 的用户 SID 与原生 Win32 API 设置受保护的 owner-only DACL；目录授予该 SID 可继承的 FullControl。禁止为此启动 PowerShell / `Set-Acl`，避免域信任或域账户解析失败阻塞配对。权限设置失败必须停止写入，保留既有凭证。

## 8. 移动端（Capacitor）专项

- **WebView 兼容下限**：共享前端使用 Tailwind CSS 4 与 Vite 8，iOS 最低版本为 **16.4**（WKWebView/Safari 16.4），Podfile 与所有 Xcode deployment target 保持一致。Android 最低 API 24 与 WebView 引擎版本是两个独立条件：实际运行需 Android System WebView / Chrome **111+**，旧设备须更新 WebView；提高 Android API 不能代替引擎版本检查。浏览器下限与依据见 [Tailwind 官方兼容说明](https://tailwindcss.com/docs/compatibility)。
- **颜色降级**：共享卡片、用量与技能表单的混色变量通过 `@supports not (color: color-mix(...))` 回退到现有主题 token，避免旧 WebView 在变量消费时生成无效颜色，导致白边或透明底色。PostCSS 入口的 `color-mix-border-fallback.mjs` 同时覆盖直接声明与 Tailwind 生成的主题混色边框，保留媒体条件、状态选择器、显式备用色和后续覆盖。CSS 自定义属性中的未知函数不会自动触发 `var()` 的默认值，不能只追加同名变量或消费处的备用声明；该降级不代表支持低于上述下限的完整运行环境。

- **安装器图标**：Windows NSIS 安装/卸载程序显式使用桌面 ICO，NSIS 与 MSI 向导位图由 `pnpm brand:assets` 从 `resources/native-icon.png` 生成并提交；`pnpm brand:assets:check` 同时检测安装器素材是否过期。macOS app/DMG 与 Linux 桌面入口继续使用 Tauri 生成的 ICNS/PNG；Android/iOS 沿用移动端原图。

- **应用图标**：`frontend/resources/mobile-icon.png` 是 512×512 RGBA 原图，底板纯白且不透明；由 `pnpm brand:assets` 同步 Android launcher、`resources/icon.png` 与 1024×1024 RGB iOS AppIcon（无 alpha 通道），`pnpm brand:assets:check` 校验一致性。系统负责移动端外轮廓裁切，不在原图画圆角。桌面端独立使用 `resources/native-icon.png`，Web 图标继续沿用现有素材。
- **流程**：改 WebView 代码后 `pnpm mobile:sync` 重新同步；`android/`、`ios/App/` 的 diff 必须人工过目后再提交，防止 sync 静默改坏原生配置。
- **版本**：`versionCode` 按 AGENTS.md 的核心版本加构建序号公式计算；`versionName` 使用统一核心版本，dev.N 使用构建序号 N，正式版使用 999，禁止绕过统一版本预检。
- **安全红线**：`allowMixedContent: false` 不动摇，API 一律 https；敏感数据不进 WebView localStorage，走原生侧或后端会话。
- **发布产物现状**：Android 出签名 APK（密钥在 CI secrets，降级 debug APK 需在 Release notes 标注）；iOS 当前为 unsigned xcarchive——签名链路上线前按 §11 推进。

## 9. 版本与发布（§ AGENTS.md 发版流程的客户端细化）

- 六文件 bump 规则以 `AGENTS.md` 为准；`versionCode`（第七处）随 `versionName` 联动。
- **cargo `Cargo.toml` crate 版本当前已漂移（2.8.6 vs `tauri.conf.json` 2.10.1）且 preflight 不校验**——二选一，团队拍板：纳入 preflight 一并 bump（推荐），或在 `Cargo.toml` 注释明确「crate 版本不参与发版」并写明理由。悬空不管是最差选项。
- 建议 bump 脚本化（`scripts/bump_version.py`：一次改齐全部版本文件 + 校验 versionCode 规则），替代手工六处编辑；出 tag 的 preflight 继续兜底。
- 正式版发版完成判据不变：latest.json 三个桌面平台条目齐全（Windows x64、macOS Apple Silicon / Intel）（含 `darwin-x86_64`）+ mac/windows 真机抽检通过。

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
