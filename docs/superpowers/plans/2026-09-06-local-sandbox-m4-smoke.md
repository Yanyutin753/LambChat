# 本地沙箱 M4 自测记录（Linux 全量）

- 日期：2026-09-05/06
- 环境：Ubuntu 26.04、MongoDB 8.2.5 临时实例、Redis 本机、后端 worktree :8000、vite :3002、sidecar 重打（13.7MB，M4 全部客户端改动后）

## 质量门（全绿）

| 门 | 结果 |
|---|---|
| `make lint` / `make typecheck` | 通过 / 475 文件无问题 |
| 后端+client 全量 `uv run pytest tests -q` | **4016 passed, 1 skipped** |
| 前端 `pnpm test` | **2201 passed**（修复 1 个失同步守门：releasePackagingSource 的 mac target 断言随动 aarch64，commit 615094e7） |
| `pnpm run build` | eager JS **510860/512000**（预算内；M4-T8 从超限 512256 拉回） |
| `cargo build` / `cargo test --lib` | 通过 / 7 passed |

## 实链自测（五项全过）

| # | 验证项 | 结果 |
|---|---|---|
| ① | 壳起 → sidecar 在线 | ✅ `{"online":true,"daemon_version":"0.1.0","daemon_platform":"linux"}`（**平台上报全链生效**） |
| ② | kill -9 自愈 | ✅ restarting(1/3) 日志、client_id 更换（ce23…→b099…）、无互踢 |
| ③ | **SIGTERM 直杀壳进程（M3 遗留缺口收敛）** | ✅ 日志「SIGTERM received; stopping daemon and exiting」→ daemon 优雅停 → offline → 零孤儿进程（宽限窗口内短暂 2 进程为正常停机中） |
| ④ | self-update 源码运行护栏 | ✅ 拒绝替换 `__main__.py`：「仅支持打包后的二进制自更新…」，exit 1 |
| ⑤ | **服务端 min-version 拒连（SANDBOX_MIN_DAEMON_VERSION=99.0.0）** | ✅ daemon 收 426 → 「客户端版本过低…请运行 lambchat_sandbox update」→ **停机退出（exit 1），不退避重连** |

另：M4-T4 已真实验证内嵌解释器（PBS 20260901/3.12.14，`sys.executable` 命中 `~/.lambchat/python/` 下）；M4-T8 实测托盘五语、裁权后壳正常起 daemon、PBS 资源落位。

## 已知边界（win/mac 真机留验）

- Job Object/父监视/fs op/cmd 引用/PBS Windows 布局：Linux 上 mock+字符串断言全覆盖，真机行为挂 **CI 三平台矩阵（T9 已接线，首次 tag/workflow_dispatch 验证）** 与人工后验
- CI win/mac runner 首跑前建议手动 workflow_dispatch 空跑一轮
- macOS universal（lipo 双架构）与 Seatbelt 沙箱列 M5；Windows 壳进程探活（process_alive）为 M5 候选
- PWA 预算余量仅 1140B，根治（locale 按需加载）列 M5

## 结论

M4 交付面（平台抽象/Windows Job Object/命令生成分支/结构化 fs op/内嵌解释器/min-version 拒连/self-update/配对重构/壳侧收口/CI 三平台）实现完成；Linux 侧全部自测通过；三任务批次+两合并批次+大批次均经独立审查（发现并修复 Critical×1[移动端误判]、Medium×5、以及 SIGKILL 不重启等实机问题）；win/mac 真机验证边界如实留档。
