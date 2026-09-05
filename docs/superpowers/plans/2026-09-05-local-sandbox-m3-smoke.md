# 本地沙箱 M3 端到端自测记录

- 日期：2026-09-05
- 环境：Ubuntu 26.04（有桌面/托盘）、MongoDB 8.2.5 临时实例、Redis 本机、后端自 worktree（feat/local-agent-desktop）:8000、vite dev :3002、sidecar 二进制 = PyInstaller 打包（13MB，T1 产物 16:26 重建版含 PDEATHSIG）
- 壳：`pnpm dlx @tauri-apps/cli@2.11.2 dev --config '{"build":{"beforeDevCommand":"","devUrl":"http://localhost:3002"}}'`

## 结果

| # | 验证项 | 结果 |
|---|---|---|
| 1 | 壳启动 + sidecar 自动拉起 + 连接 | ✅ `daemon sidecar started` → status `{"online":true,"daemon_version":"0.1.0"}`（版本全链上报） |
| 2 | 托盘构建 | ✅ 无 `tray unavailable` 告警（菜单交互留日常使用验证） |
| 3 | **SIGKILL 自愈（T8 核心发现→修复→复验）** | ✅ `kill -9` onefile 包装进程 → ≤5s 日志 `restarting (1/3)`、新 client_id（46b6…→9525…）、旧孤儿经 PDEATHSIG 被内核回收、进程数收敛 2 |
| 4 | 退出清理（正常路径：关窗口） | ✅（Rust 批次 smoke 验证：无孤儿进程） |
| 5 | 配对 UI / 选择器 / 网页动态适配 | ✅ 组件级（2175 前端测试含互斥模态/四象限矩阵/配对链路顺序）；浏览器端手工验证留日常使用（web 端矩阵 = daemon 在线才出现本地档，逻辑在纯函数层已锁） |
| 6 | agent 完整跑一轮本地沙箱会话 | ⏸ 本地 DB 无模型配置，无法真实跑 LLM——**staging（有模型）回归项**，与 M1/M2 相同的已知边界 |

## 自测发现并已修复的问题（T8 价值所在）

1. **SIGKILL 不重启（Critical，fix round 2 修复 48477fc7）**：tauri-plugin-shell 2.3.6 的 Terminated 事件依赖 stdout 管道 EOF 释放读锁；PyInstaller onefile 内层继承管道写端 → 杀包装进程后管道永不 EOF、插件 wait 线程死锁、监视线永不触发。修复：壳侧改 `kill(pid,0)` 探活轮询（libc/unix）+ 通道仅排空；复审者独立复现 PDEATHSIG 行为。
2. **孤儿互踢（随 1 一并发现修复）**：原假设"孤儿被新连接踢掉后 15s 自行退出"不成立——daemon 把被踢当瞬断无限重连互踢。修复：client 入口 `PR_SET_PDEATHSIG(SIGKILL)`（父=onefile 包装进程），内核级随父死亡，实测 t≈3s 收敛。

## 已知边界（记录在案，不阻塞 M3）

- **SIGTERM 直杀壳进程不走退出清理**：daemon 树被 systemd 收养并稍后重连恢复在线（实测 offline 54s 后回 online）。正常路径（关窗口→Exit 事件→stop）已验证可用；M4 加 SIGTERM 处理器收敛此路径。
- 故意 stop 走 SIGKILL 无 post_offline：offline 靠服务端 TTL（≤35s）；M4 可改 SIGTERM+宽限再收尸。
- PDEATHSIG 仅 Linux（勘误：初记"当前发布矩阵 unix/Linux"不成立——app-release.yml 本就含 Windows/macOS 桌面矩阵；实况是 win/mac 缺 daemon 构建步（属 M4），desktop 子矩阵已临时注释下线至 M4 恢复，macOS/Windows 的孤儿治理届时一并处理）。
- RunModePopover 常挂第二个状态轮询实例（流量浪费，M4 门控）；badge 显示原值的 cosmetic 差。
- tauri.conf.json devUrl=5173 与仓库 vite 实际端口不匹配（仓库从未跑过 tauri dev）：本记录用 --config 覆盖；M4 打包链路走 packaged build 不受影响，dev 脚本可固化此覆盖。

## 结论

M3 交付面（sidecar 生命周期/自愈、配对命令链、托盘、前端动态适配矩阵、i18n×5）实现完成；三批次均经独立审查与修复环（R1×2、R2×1），自测 6 项中 4 项实机通过、1 项组件级覆盖、1 项留 staging。安全相关修复（符号链接逃逸/双派生竞态/SIGKILL 自愈/孤儿回收）均有变异式或实机证据。
