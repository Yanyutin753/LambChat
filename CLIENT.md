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
- Android 使用 JDK 21，SDK 版本以 `frontend/android/variables.gradle` 为准，Gradle 使用仓库 wrapper；本地 `JAVA_HOME` / `ANDROID_HOME` 指向独立工具链，不提交 `local.properties`。构建经共享验证锁运行，Gradle 指定 `--max-workers=1 --no-parallel`。
- iOS 依赖 CocoaPods 与完整 Xcode/iOS SDK，仅安装 Command Line Tools 不能编译 iOS。`mobile:sync` 会同步两个移动平台；仅验证 Android 时可在前端构建后运行 `cap sync android`，`cap copy ios` 只算资源复制，不算 iOS 原生验证。
- PBS runtime 与 PyInstaller 版本必须 pin 精确版本，禁止 `latest`；升级单独 PR。
- daemon 打包使用 `uv.lock` 中的 `daemon-build` 组（含 `cua`），安装到 `client/build/venv`，不安装服务端依赖或改动开发环境。更新器校验使用同一 Cargo workspace 内的 `lambchat-updater-verifier`，复用真实校验源码和锁定版本，只编译校验需要的依赖。
- 本地开发起点：`make client-fetch-pbs` + `make client-build-daemon`；建议补 `make dev-desktop` 一键拉起桌面开发壳（§11）。

## 4. 依赖（§4）

- **daemon 保持 stdlib + httpx 的极简依赖面**，新增依赖必须在 PR 说明理由（PyInstaller onefile 体积与冷启动对此敏感）。既有例外：computer-use 的 `cua` 依赖组（`uv sync --group cua`，平台标记互斥）——macOS atomacos（带 PyObjC+pyautogui）、Windows pywinauto+pyautogui、Linux pyautogui+python-xlib（AT-SPI 走系统包 python3-pyatspi）；未同步该组的构建里 cua\_\* op 报 `unsupported_platform`，其余链路不受影响。
- CUA 必须显式选择在线机器；代码沙箱可为本地或云端，桌面选机与代码沙箱平台独立。工具参数不能覆盖会话选机，未选择、离线或审批后改机均拒绝，不回退到账户默认机器。审批绑定机器和具体操作，按该机器确认策略执行。观察索引仅在当前会话有效。
- 桌面构建内嵌 `client/agent-desktop.lock.json` 锁定的 agent-desktop 与平台 helper，构建期核验 SHA256，不在运行期自动下载或执行 PATH 中的同名程序。许可证随 daemon 分发。开发环境可通过 `LAMBCHAT_AGENT_DESKTOP` 指定二进制；未安装资源时保留原生后端。新驱动继续遵守前台截图、显式激活与机器审批边界，不开放其任意 CLI/MCP 命令。
- 桌面壳托管的 CUA 使用每显示器全屏透明提示层与独立置顶接管控制条，经继承的 stdin/stdout 管道握手；所有提示层和控制条绘制确认后才执行。提示层不获取焦点、鼠标穿透且只有只读 IPC 权限。浮窗在 Agent 思考间隔继续显示，用户暂停会取消当前工作进程并拒绝后续 CUA 调用；恢复必须重新观察，前台冲突自动暂停。控制绑定可信 session_id/run_id，每次输入前及控制期间通过 PAT 鉴权核对具体执行仍在 running；终态、换轮或断连取消输入后隐藏控制界面，思考间隔不隐藏。用户接管状态跨任务保留，仅本机控制条可恢复；断管与握手超时拒绝执行，不禁用用户系统键鼠。独立 CLI daemon 不具备壳浮窗。新增壳命令 `desktop_control_status(ready) -> state` 与 `desktop_control_set_paused(paused)` 仅授予 `cua-control` 窗口；旧 daemon 忽略新增环境变量，协议兼容，但浮窗需新版壳与 daemon 同时具备。Mac/Windows 浮窗设置 `content_protected`；Linux X11 直接读取目标窗口的 XComposite 离屏像素，保持浮窗可操作且不进入截图。缺少 XComposite、运行中的 X11 合成器或无法确认目标窗口时拒绝截图，不回退到含浮窗的桌面截图；Wayland 截图仍不支持。
- CUA 观察和输入在独立常驻工作进程内执行，超时或取消后回收进程树与临时快照目录；Windows 使用 Job Object。应用启动独立于该工作进程，避免回收自动化进程时关闭用户应用。恢复后必须重新观察，不自动重放输入。Agent 光标使用上游 overlay，平台不支持绘制时不把展示失败当作语义动作失败。
- `state` 回传 `snapshot_id`；使用截图像素坐标时必须传该 ID 与 `coordinate_space=screenshot`，daemon 校验会话、窗口焦点及位置并完成缩放换算。服务端使用独立 `cua_snapshot_action` 操作，旧 daemon 明确拒绝，不会把截图坐标误当全局坐标。原有全局坐标与未带快照 ID 的调用保持兼容。动作的 `disposition` 区分已验证、未验证和不确定交付；工具成功不能替代应用最终状态验收。
- 命令 stdout/stderr 通过非阻塞管道读取并分别保留有界尾部，禁止先收集完整输出再截断；Windows 需要项目既定的 Python 3.12+ 管道支持。
- 远程服务器地址必须使用 HTTPS，HTTP 仅允许回环开发地址。PAT 绑定签发服务器 origin，改连服务器不复用旧凭据，未绑定的旧凭据须重新配对；服务器反向代理子路径仍保留。凭据文件原子写入，并在写入内容前设置仅本用户可访问的权限。
- 上述传输与账户隔离不等同于服务器失陷后的端到端控制隔离：当前电脑指令仍由服务端 Agent 生成。可信设备执行与端到端配对方案须独立实现、验证后才能声明服务器无控制权。
- daemon 的有界 call_id 去重同时记录请求终态：结果已受理（含流式结果）或服务端明确拒绝过期回传后，重复帧仅记审计并跳过 HTTP；结果尚未确认的重复帧仍补发 ACK，避免旧终态调用阻塞后续请求。
- daemon 最多并发执行 8 个调用，接收通道不等待长命令结束；最多保留 64 个运行/排队调用，超出时明确返回 busy。同一解析后文件路径（含符号链接别名）串行，硬链接及非传输文件操作作为文件队列的顺序屏障；桌面操作按到达顺序串行。Agent 同时发出的 exec 可与其他调用并行，有文件依赖的命令须等待前一工具结果后再提交。排队调用立即 ACK，排队时间计入原超时预算，过期后不得执行。活动调用不因去重环轮转而被遗忘，通道失败或退出须取消并回收全部调用任务，不自动重放写入。
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
- **macOS 特例**：ad-hoc 签名（`signingIdentity: "-"`）+ `hardenedRuntime: false` 是 PBS sidecar 内嵌 dylib 的既定兼容决策，改动此项必须附 macOS 自动化签名与启动验证结论，真机抽测可选；不得放宽 CI 签名校验与 Gatekeeper 兼容要求。
- **sidecar 生命周期契约**：退避重启（上限 3 次、稳定 300s 重置计数）、`kill(pid,0)` 存活探测、SIGTERM 优雅退出、`RunEvent::Exit` 兜底回收——**凡动 `daemon.rs` 或 daemon 进程管理（`procsup.py`），合并前必须跑 `uv run python scripts/e2e_local_sandbox.py` 全绿**（AGENTS.md 硬性门禁）。
- **升级保留数据**：升级或同版本重装不得递归删除 app data / WebView 数据目录；登录、偏好和窗口状态随版本保留。前端资源通过构建产物文件名更新，禁止为刷新资源而清空持久化数据。
- **关闭到托盘的降级**：系统关窗请求仅在主窗口且托盘创建成功时隐藏窗口；托盘缺失时最小化，保留任务栏/Dock 恢复入口。预览窗口仍正常关闭，自绘标题栏既有退出行为不变。
- **Linux 安装来源探测**：`dpkg/rpm` 查询放在后台阻塞线程，每次探测最多 3 秒；丢弃探测输出，超时回收进程组并沿用未知来源的下载页回退，不阻塞窗口线程。
- **连接和资源恢复**：通知 WebSocket 的握手及认证最多等待 15 秒，超时即隔离旧连接并按已有退避重连，不依赖系统发送 close 事件；认证成功、账户切换及卸载均清理计时器。资源加载失败仅在确实发起自动重载时吞掉异常，冷却期或存储不可用时保留错误边界和手动刷新入口。
- **网络等待与资源释放**：用户资料初始化、版本 API、定时任务 CRUD/操作及 Windows/macOS 原生更新检查最多等待 30 秒；JSON 请求计时覆盖响应正文，保留调用方取消信号；定时任务超时释放界面忙碌状态，不自动重放创建或执行请求。原生更新下载最多 30 分钟，失败、跳过或丢弃的更新对象须释放，待安装对象保留到安装或用户丢弃。原生 API 地址改写须保留 `Request` 的取消、凭据、缓存及重定向策略。
- **日志**：统一写 `~/.lambchat/logs/desktop.log`，禁止另起路径；日志里不得出现 token / pairing 凭据明文。
- **Windows 凭证权限**：使用进程 token 的用户 SID 与原生 Win32 API 设置受保护的 owner-only DACL；目录授予该 SID 可继承的 FullControl。禁止为此启动 PowerShell / `Set-Acl`，避免域信任或域账户解析失败阻塞配对。权限设置失败必须停止写入，保留既有凭证。

## 8. 移动端（Capacitor）专项

- **WebView 兼容下限**：共享前端使用 Tailwind CSS 4 与 Vite 8，iOS 最低版本为 **16.4**（WKWebView/Safari 16.4），Podfile 与所有 Xcode deployment target 保持一致。Android 最低 API 24 与 WebView 引擎版本是两个独立条件：实际运行需 Android System WebView / Chrome **111+**，旧设备须更新 WebView；提高 Android API 不能代替引擎版本检查。浏览器下限与依据见 [Tailwind 官方兼容说明](https://tailwindcss.com/docs/compatibility)。
- **颜色降级**：共享卡片、用量与技能表单的混色变量通过 `@supports not (color: color-mix(...))` 回退到现有主题 token，避免旧 WebView 在变量消费时生成无效颜色，导致白边或透明底色。PostCSS 入口的 `color-mix-border-fallback.mjs` 同时覆盖直接声明与 Tailwind 生成的主题混色边框，保留媒体条件、状态选择器、显式备用色和后续覆盖。CSS 自定义属性中的未知函数不会自动触发 `var()` 的默认值，不能只追加同名变量或消费处的备用声明；该降级不代表支持低于上述下限的完整运行环境。

- **安装器图标**：Windows NSIS 安装/卸载程序显式使用桌面 ICO，NSIS 与 MSI 向导位图由 `pnpm brand:assets` 从 `resources/native-icon.png` 生成并提交；`pnpm brand:assets:check` 同时检测安装器素材是否过期。macOS app/DMG 与 Linux 桌面入口继续使用 Tauri 生成的 ICNS/PNG；Android/iOS 沿用移动端原图。

- **应用图标**：`frontend/resources/mobile-icon.png` 是 512×512 RGBA 原图，底板纯白且不透明；由 `pnpm brand:assets` 同步 Android launcher、`resources/icon.png` 与 1024×1024 RGB iOS AppIcon（无 alpha 通道），`pnpm brand:assets:check` 校验一致性。系统负责移动端外轮廓裁切，不在原图画圆角。桌面端独立使用 `resources/native-icon.png`，Web 图标继续沿用现有素材。
- **流程**：改 WebView 代码后 `pnpm mobile:sync` 重新同步；`android/`、`ios/App/` 的 diff 必须人工过目后再提交，防止 sync 静默改坏原生配置。
- **Android 更新下载**：系统下载与 WebView 备用下载均限制为 60 秒无进展、总计 30 分钟。系统任务失败或停滞后先调用 `UpdateDownloader.cancel` 移除任务，成功取消后才能开始备用下载；旧壳缺少取消方法或取消失败时明确结束本轮并报错，不并行启动备用下载。原生查询异常必须 reject 插件调用；备用流下载在异常时释放 reader、清理半截缓存，完成后核对 Release 提供的大小再启动安装器。
- **版本**：`versionCode` 按 AGENTS.md 的核心版本加构建序号公式计算；`versionName` 使用统一核心版本，dev.N 使用构建序号 N，正式版使用 999，禁止绕过统一版本预检。
- **安全红线**：`allowMixedContent: false` 不动摇，API 一律 https；敏感数据不进 WebView localStorage，走原生侧或后端会话。
- **发布产物现状**：Android 出签名 APK（密钥在 CI secrets，降级 debug APK 需在 Release notes 标注）；iOS 当前为 unsigned xcarchive——签名链路上线前按 §11 推进。

## 9. 版本与发布（§ AGENTS.md 发版流程的客户端细化）

- 六文件 bump 规则以 `AGENTS.md` 为准；`versionCode`（第七处）随 `versionName` 联动。
- `Cargo.toml` crate 版本参与运行时版本及发布预检，必须与 `tauri.conf.json` 和 AGENTS.md 所列版本文件同步，不能豁免。
- 建议 bump 脚本化（`scripts/bump_version.py`：一次改齐全部版本文件 + 校验 versionCode 规则），替代手工六处编辑；出 tag 的 preflight 继续兜底。
- 正式版发版完成要求 CI、打包冒烟、签名校验和自动化回归通过，latest.json 三个桌面平台条目齐全（Windows x64、macOS Apple Silicon / Intel，含 `darwin-x86_64`）。Mac、Windows 及手机真机检查可选，未测不阻塞发布。

### 模型调用与跨端一致性

- Web、Tauri（macOS / Windows / Linux）、Capacitor（Android / iOS）共享助手目录与五语文案；轻量助手保留 `quick` 标识，已有会话和助手偏好继续有效。
- 所有已注册模型协议共用瞬态错误分类：连接故障、超时、408 / 409 / 429 / 5xx 按 `LLM_MAX_RETRIES` 和 `LLM_RETRY_DELAY` 重试。主模型失败后使用模型配置或全局配置中的 fallback；401 / 403 直接切备用模型，不重试相同凭据。
- 轻量助手的直接调用也使用共享重试 / fallback；直接调用已经交付流式内容后不重放请求，取消立即传播。备用模型失败后终止，不循环切换。
- 桌面烘焙期间自动更新主端点回退到最近已发布稳定版清单；手动检查直接依据返回的版本结果反馈，检查、下载和待安装状态不互相覆盖。

## 10. 测试（§5 + §10）

每次正式版或测试版出包后执行 `make -j1 release-regression RELEASE_TAG=<明确 tag>`，默认只运行生产自动化回归和跨端浏览器模拟，不连接真机。Windows 真机脚本及 Mac 走查均可选，不影响发布；操作说明见 `scripts/release_tests/README.md`，各类验证结果分别记录。

| 层 | 现状 | 要求 |
|----|------|------|
| TS / React | vitest（CI 有） | 沿用 AGENTS.md TDD 流程 |
| Rust | `lint.yml` 已有 `cargo test --lib`，单 worker / test thread | `daemon.rs` / `tray.rs` 改动补单测；平台专属代码仍需对应 runner 验证 |
| daemon 链路 | `e2e_local_sandbox.py`（硬性门禁） | 涉及沙箱链路必跑；发版前加 `--stress` |
| 打包产物 | CI 冒烟门禁（mac/Linux/Windows 三式） | 不豁免；新平台/新包型先补冒烟再合 |

## 11. 落地清单（本规范生效后的补课项）

| 优先级 | 事项 | 对应章节 |
|--------|------|----------|
| P0 | Rust fmt/clippy 配置 + CI 步骤 | §5 |
| P0 | 版本 bump 脚本化 | §9 |
| P1 | VitePress「客户端开发」章节 | §2 |
| P1 | `make dev-desktop` 一键桌面开发壳 + `rust-toolchain.toml` | §3 |
| P2 | CSP 收紧方案 | §7 |
| P2 | iOS 签名链路 | §8 |

### 桌面原文件附件

桌面本机沙箱中的原生文件选择、拖拽只添加原文件路径，不复制、不上传；修改直接作用于原文件。云端、其他机器环境和 Web/移动端仍使用上传附件，云端图片压缩规则保持一致。切换环境只转换待发送附件，不批量上传历史本地文件。剪贴板中没有原路径的 Blob 仍走上传。

`commands/attachments.rs` 的 `desktop_pick_files(title)` 返回原生选中文件的路径元数据与 opaque receipt；原生 drop 通过 `desktop-files-dropped` 的开始/完成批次事件传递同样信息。`desktop_file_info(token)` 读取最新元数据，`desktop_read_file_chunk(token, offset, length, size, modified)` 每次最多读 1 MiB 并拒绝读取期间发生变化的原文件，`desktop_reveal_file(token)` 在文件管理器定位原文件。四个命令仅授予主窗口 `allow-desktop-file-references` capability，不能传任意路径读取；receipt 保存在应用数据目录 `file-references/`，只记录元数据，不复制文件内容。

本地附件协议向后兼容旧云端附件；`localFile` 携带原路径、所属 machine ID 和客户端 receipt。服务端要求本地环境、支持沙箱的 Agent 和当前用户拥有的匹配在线机器。复用既有绝对路径沙箱执行与审批，不新增 daemon 操作，不降低文件执行审批。路径文件需要模型看图时仍会传输必要内容并在服务端转换/压缩，但不要求存入对象存储。浏览器模拟不代表原生拖拽真机验收。

Windows 主窗口使用 WebView2 的 HTML 拖拽，关闭仅识别普通路径的 Wry 拖拽拦截。主窗口通过 `postMessageWithAdditionalObjects` 提交真实 `File` 对象，原生 `windows_file_drop` 桥校验固定应用来源后读取 `ICoreWebView2File.Path` 并签发现有 receipt；不接受前端文本路径。没有原路径的图片字节使用现有上传、云端压缩流程，无法读取的占位内容明确提示。异步回传绑定账户、服务器、对话和环境；桥接等待最多 3 秒，超时可改用原生选择文件。

桌面文件下载统一经 `desktop_save_file`：二进制 IPC 传入文件内容，`x-file-name` 为 ASCII 转义的 JSON 文件名；原生另存为对话框决定目标路径，主窗口 `allow-desktop-save-file` 权限不接受任意写入路径。取消正常结束，保存失败显示现有下载失败提示；同目录临时文件完整写入后替换目标，失败清理临时文件。Windows CI 编译原生桥并运行文件边界测试，仍须区分这些检查与微信拖拽/系统保存对话框的人工验收。

## Android 本地设备

- Android 11+ / arm64 可在设置 → 本地设备配对并启动；其他架构保留聊天能力，不显示为可用执行端。模型和审批仍由 LambChat 服务端负责，安卓运行同一套 `lambchat_sandbox` daemon，SSE/文件协议向后兼容。
- 原生 `LocalDevice` Capacitor 插件桥接配对、策略、启停、系统文件选择器及用户主动操作的手机控制设置。凭据用 Android Keystore 加密，身份、凭据、工作目录均位于 no-backup 私有目录；服务器 origin 不一致时不返回 PAT。取消配对不删除工作文件。
- PRoot + Alpine（Python / Node / Shell）随 APK 打包，首次启动离线展开。手机文件通过系统选择器复制到 `/workspace/.shared`，导出使用系统保存对话框；无需全盘存储权限，不访问其他应用私有目录。共享列表最多 200 项，单次导入导出限 512 MiB；会话文件继续使用现有文件面板。PRoot 不是恶意代码隔离边界，执行权限相当于应用用户权限。
- 前台服务有常驻通知和停止操作；退出任务列表后停止，不自动重放命令、不自动重启服务。系统仍可能回收后台进程，重新打开应用后在本地设备设置重启。手机 App 控制从 Android 12 起提供，独立焦点的后台 App 操作要求 Android 14+；不满足时须由用户主动选择前台模式，不自动抢占主屏。桌面驱动不在 Android 上兜底。
- 修改后在共享验证锁下准备运行环境，再构建原生工程：
  ```bash
  # 本机已有独立工具链时可先 source "$HOME/.cache/lambchat/client-toolchains/env.sh"
  python3 scripts/run_validation.py uv run python scripts/prepare_android_runtime.py
  cd frontend/android && python3 ../../scripts/run_validation.py ./gradlew testDebugUnitTest assembleDebug --max-workers=1 --no-parallel
  ```
  构建失败不得跳过运行环境校验。依赖固定于 `scripts/android-runtime/sources.json`；原生程序和 rootfs 校验 SHA-256。产物仅写入 `frontend/android/app/build/generated/localDevice/`，不提交二进制。
- 悬浮窗：在本地设备设置中单独启用，Android 系统实际授予悬浮窗权限后才开启；App 在后台时显示连接/执行状态，支持拖动吸边、展开、返回 App、停止本地执行和隐藏。折叠时只显示数量和状态；展开后支持当前对话的任务输入、系统语音转文字、截屏导入共享目录、无表单审批、暂停/恢复及接管。表单审批返回现有 App 面板。审批核对原始请求和当前会话，语音与截屏只填入草稿，不自动发送。权限被撤销时隐藏，停止服务时移除。
- Mika 对齐的原生验收清单（实现不等于验收通过）：手机内无线调试配对与断线恢复；App 列表/启动/切换；屏幕结构读取与截图；点击、长按、滑动、输入与返回；独立显示区域里的后台 App 操作与前后台交接；浮窗发起任务、任务状态、审批/接管/停止。所有模型操作必须经过既有设备归属检查和审批通道，不能从 WebView 直接暴露任意特权 shell。逐项记录原生设备结果，未接通的能力不能在工具清单或文案中宣布可用。
- 手机控制链路：本机无线调试配对（Keystore 包装身份）→ ADB 的私有 stdin/stdout helper → 用户授权的无障碍服务。没有可供 WebView 任意调用的 shell 执行入口。后台显示区域、应用启动、按键在 shell helper 完成；树读取、元素操作、手势、文字及截图走 Android 无障碍接口。工具沿用 `computer_use` 的选机、会话、审批指纹和私有图片上传；daemon 通过限长、随机令牌认证的 loopback 端点调用原生操作。该端点仅在本地服务运行时存在，脚本与端点同属应用用户权限，并非恶意脚本隔离边界。
- 设置引导：先启动本地设备，手动授予屏幕访问，打开无线调试的配对码对话框，可用悬浮窗输入配对端口与六位码；连接使用无线调试主页的连接端口。可发现本机 mDNS 端口，不连接其他设备。断线后不重放动作，重新发现端口并连接；停止/取消配对关闭 bridge 和 helper。接管先暂停，再将本 helper 启动的任务移回主屏；再次输入必须重新观察。后台启动遇到用户正在主屏使用的 App 时拒绝。
- 安全与兼容边界：锁屏时拒绝操作，密码控件不读取或写入，LambChat 自身、设置和权限页面不接受模型操作；快照绑定会话、包名、显示区域、窗口变化及 60 秒时效。厂商 ROM 的 shell/虚拟屏 API、受保护窗口和应用多屏兼容性仍须分别测试；不把 API 调用返回成功写成端到端效果已验证。
- 验证入口包括 `tests/client/test_android_control.py`、手机设置/浮窗桥接的前端测试、原生 `PhoneHelperTest`/ADB 加密与地址测试、`PhoneBridgeTest` 及 `LocalDeviceRuntimeTest`。设备验收至少覆盖：中文输入、长按/滑动/返回、旧截图拒绝、主屏焦点不被后台任务抢占、审批内容变更、切账号后旧浮窗事件、接管和断线清场。
- 发布 Android APK 必须先执行 `prepare_android_runtime.py --sources` 并附带 `android-runtime-sources.tar.gz`（PRoot/talloc、Alpine 的对应源码、锁文件、补丁及许可证）。上游来源、版本和许可见 `scripts/android-runtime/NOTICE.md`。原生冒烟 `LocalDeviceRuntimeTest` 需 Android 11+ arm64 模拟器或真机，运行 Python、Node、Shell、文件读写并验证取消清场；主机单测不能替代它。
