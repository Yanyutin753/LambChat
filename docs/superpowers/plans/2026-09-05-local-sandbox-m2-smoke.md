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

## 终审修复补充（2026-09-05，同日二审）

终审在冒烟基线上发现 F1–F4 四项缺陷，均已修复并补测试（提交 5ec08eea / 09324776 / 251ae30b / 23f8fa7a）：

### F1 虚拟别名路径不被翻译（5ec08eea）

`prompt_policy` 以 `work_dir=/workspace/{sid}` 指示模型用别名绝对路径调文件工具，但 daemon 只映射 cwd、不翻译命令内路径 → `/workspace/{sid}/x` 在用户本机 `file_not_found`。修法：`WorkspaceAliasBackend` 在命令构造之前的方法入口把 `/workspace/{sid}/x` 翻译为相对路径 `x`（read/ls/write/edit/glob/grep/delete/upload/download 全覆盖），返回值相对路径补回别名前缀，shell 命令串内别名改写为 `.`（负向断言防误伤更长 sid）；`nodes.py` local 分支改 wiring 该后端。

### F2 本地传输上限与误报（09324776）——实际生效上限

- **上传**：单条命令原始内容上限 **48KB**（`_UPLOAD_CHUNK_RAW_BYTES = 48 * 1024`，b64 后 ~64KB）；≤48KB 单命令直写，更大按 48KB 分块（首块 `wb` 截断创建含 mkdir、后续块 `ab` 追加）。48KB 的安全余量来自内核 `MAX_ARG_STRLEN`：单参数上限 128KB，扣除引号/命令前缀开销后 **~96KB 即触发 E2BIG**。已验证 256KB 端到端逐字节一致。
- **下载**：命令内置 `stat` 预检，单文件上限 **2MB**（`_DOWNLOAD_MAX_BYTES = 2 * 1024 * 1024` = 2,097,152 字节原始文件），超限打印显式 `file_too_large: N bytes exceeds 2097152 limit`（stderr + exit 1），不再输出注定撑爆链路的 base64。
- **服务端 results 回传 body**：`SANDBOX_RESULTS_MAX_BYTES = 2097152`（2 MiB），边界判 **`>` 而非 `>=`**（恰好 2 MiB 的 body 放行，+1 字节 413 `sandbox_payload_too_large`，见 at-limit 边界两用例）。
- 错误分类：`_classify_file_error` 识别 E2BIG/EFBIG/超限文本 → `file_too_large`；b64decode 异常不再误报 `file_not_found`。
- 留存：2MB **全量**端到端（上传/下载各 2MB 真机走通）未在本轮冒烟覆盖（上传实测到 256KB），M3 真机回归补；上传侧还可在服务端先做 content-length 总量预检（超 2MiB 直接拒绝，省掉分块下发）。

### F3 daemon ack 次序与迟到执行（251ae30b）

- ① ack 从「确认放行后」提前到「收到 tool_call 即发」（先于确认门与 op 分发）：用户盯着终端确认提示犹豫不再吃 dispatch 的 30s ack 死线（旧实现会误报 `sandbox_timeout` 而本地命令根本没跑）；确认等待改计入执行超时窗口。
- ② `_process_call` 记起始 `time.monotonic()`，确认放行后 `elapsed >= timeout`（0/缺失回落 60s 默认）→ `done(status=error, error="expired")` + 审计 `expired`，不调 executor——dispatch 的 exec 死线已到，执行结果注定无人接收。

### F4 POST 无超时（23f8fa7a）

`AsyncClient(timeout=None)` 全局默认是给 SSE 长连接用的（心跳流不能被读超时切断），不能改；`post_result`/`post_offline` 显式带 `timeout=10.0`（`POST_TIMEOUT_S`）——否则服务端半死（accept 后不回包）会让 ack/done/offline 永久挂起拖垮 daemon 主循环。测试从 `request.extensions` 断言 POST 带 10s 四项超时、SSE 流保持无超时。

### 版本地基（0bf70044，用户新需求第一步）

- `client/lambchat_sandbox/__init__.py` 定义 `__version__ = "0.1.0"`，CLI 新增 `version` 子命令。
- daemon `connect()` URL 带 `?version=`（服务端访问日志直接可见）→ channel 端点读 query 存入注册表 hash value（`node_id|version`，无 version 保持纯 node_id 向后兼容，心跳带同一 version 重写防 15s 后降级丢失）→ `GET /api/sandbox/status` 新增 `daemon_version` 字段（旧格式 null）。
- 版本策略（最低版本拒连、self-update）不在本轮：M3 Tauri 壳随版本更新 daemon / M4 独立 CLI self-update + 服务端最低版本拒连。
