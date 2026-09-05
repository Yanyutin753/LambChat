# 本地沙箱 M2 真机冒烟记录

- 日期：2026-09-05
- 环境：Ubuntu 26.04 / Redis(本机) / MongoDB 8.2.5（`~/.local/opt/mongodb` 临时实例，数据 `/tmp/m1-mongo-data`，与 M1 冒烟同库沿用 m1_smoke 账号）/ 后端自 worktree `sandbox-m2-client` 以 `uv run python main.py` 启动
- 客户端：`PYTHONPATH=client uv run python -m lambchat_sandbox`（CLI）

## 结果（8/8 通过）

| # | 验证项 | 结果 |
|---|---|---|
| 1 | CLI `login` 配对（管道喂 getpass，回退 stdin 警告但可用） | ✅ 打印 `配对成功：PAT lc_pat_0… 已存储` |
| 2 | `status` 离线 → daemon `run` → 在线（client_id 一致） | ✅ `{"online":false}` → `{"online":true,"client_id":"14b8c5ecffc6"}` |
| 3 | 跨进程 `dispatch_local_call` exec 往返（policy=none 自动放行） | ✅ `pwd > marker.txt` → `~/.lambchat/workspaces/m2-smoke/marker.txt` 内容为映射后的真实路径 |
| 4 | `LocalSandboxBackend.aread`（BaseSandbox 继承的文件读，经真 daemon 执行 python3 脚本） | ✅ 读 `/etc/hostname` 返回结构化 ReadResult |
| 5 | 确认交互（policy=all + FIFO 喂 y）：变更命令 `echo … > confirmed.txt` | ✅ 放行执行，`confirmed.txt` 落盘 |
| 6 | 确认交互（喂 n）：`echo … > denied.txt` | ✅ 拒绝：dispatch 收到 `sandbox_exec_failed / declined_by_user`，`denied.txt` 不存在 |
| 7 | **SIGTERM 优雅下线**（T7 offline 端点） | ✅ **12ms** 翻转 offline（curl 10ms 级轮询实测；对照 M1 无 bye 通知时 15–35s 心跳窗口），daemon 日志「收到中断，已优雅下线」 |
| 8 | 审计 JSONL | ✅ `~/.lambchat/audit/{daemon,m2-smoke,m2-confirm}.jsonl` 含 received/allowed/executed/declined/shutdown 全事件链 |

## 观察备注

- 工作区映射实测：服务端下发的虚拟 cwd `/workspace/m2-smoke` 在 daemon 侧落为 `~/.lambchat/workspaces/m2-smoke`（marker.txt 的 pwd 证明）。
- 拒绝路径的错误语义：daemon 回 `done(status=error, error="declined_by_user")`，服务端 dispatch 转成 `SANDBOX_EXEC_FAILED(detail=declined_by_user)`——agent 可读到拒绝原因。
- 精确计时方法备注：首次粗测（uv run 逐轮查询）报 14s 系工具启动开销污染；改 curl/urllib 100ms 轮询后实测 12ms。
