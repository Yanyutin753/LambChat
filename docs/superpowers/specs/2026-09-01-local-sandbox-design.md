# LambChat 本地沙箱设计（v2）

- 日期：2026-09-01（v2 全量重写，替代同日 v1「本地 Agent 桌面客户端」方案，见 §1 取舍）
- 状态：待评审
- 分支：`feat/local-agent-desktop`

## 0. 决策记录

| 决策点 | 结论 | 备注 |
|---|---|---|
| 总方向 | **服务端 agent 不动 + 本地执行后端**：全部功能留在服务端，仅文件/代码执行落用户本机 | v1 的模型网关、ingest 端点、本地 agent 图全部放弃 |
| 传输 | **SSE 下行 + POST 上行**（弃 WS） | WS 握手/upgrade 慢、半开断联不可知；SSE 是 LambChat 生产已验证通道（聊天流式） |
| 断联治理 | 心跳 15s + 注册表 TTL + 状态 UI 可见 + 下发前 fail-fast | 见 §3.2/§6 |
| 隔离方式 | 子进程 + 目录边界（软隔离） | Docker 容器列为后续可选增强，不进 v1 |
| daemon 形态 | sidecar 打进现有 Tauri 桌面壳 | 随壳安装/升级，用户只装一个 app |
| 离线回退云端 | 默认**关**，可配置 | 选本地即有意让数据落本地，静默切云端危险 |
| 确认策略 | 本地写文件/执行命令默认经 HITL 网页确认 | 复用 `ask_human` 既有交互，可配置放开 |
| 形态依据 | 2026-09 两轮业界调研后定稿：**Devin Outposts 同构**（云 brain + 本机执行 + 仅出网拨号）；产品定位 = 网页功能零改动 + 本机作执行基座 | 见 §12 |

## 1. 背景与目标

v1 方向（本地独立 agent）的问题是"本地模式"必然缺失 memory、技能、MCP、搜索、团队、HITL 等全部服务端能力，违背"其他所有功能正常使用"的要求。v2 反转执行位置：**agent 图与全部工具生态留在服务端原样运行，仅把"文件读写 + 代码/命令执行"的落点搬到用户本机**。用户在网页端照常聊天，会话选择"本地沙箱"后，文件与执行工具即落到本机执行。

**已知取舍（如实声明）**：本架构下本地文件内容、代码与执行结果会流经服务端（agent 需要读取、LLM 调用从服务端发出）。"直连"的意义是免手动上传、读写落在本机磁盘，**不是内容不出本机网络**；内容不出门只有本地 agent 方案可做到，已在 v1→v2 取舍中放弃。

**非目标**：本地运行 agent / 模型网关 / 消息 ingest；移动端；Docker 硬隔离（后续可选）；服务端向客户端发起入站连接；超长任务（>可配超时上限）。

## 2. 总体架构

```
用户机器                                LambChat 服务端
┌──────────────────────────┐  单向出网   ┌────────────────────────────────┐
│ Tauri 桌面壳（现有）        │           │ Agent 图照常跑（全功能不变）        │
│  └ sandbox daemon(sidecar) │──SSE──▶   │  /api/sandbox/channel 持连接进程 │
│     ├ 文件读写（roots 内）   │◀─POST──   │  Redis 路由 ← arq/API 其他进程    │
│     ├ 子进程执行            │  结果回传   │  LocalSandboxBackend（与 E2B/   │
│     ├ 心跳/重连             │           │   Daytona/Cube 平级的后端实现）    │
│     └ 审计日志              │           │  会话沙箱路由：cloud | local      │
└──────────────────────────┘           └────────────────────────────────┘
        界面完全用现有网页端；确认弹窗复用现有 HITL
```

## 3. 服务端新增（M1）

### 3.1 PAT 个人访问令牌（瘦身版）

daemon 常驻连接不能存用户密码，JWT 周期太短：

- 端点：`POST/GET/DELETE /api/auth/pat`（创建 `{name, scopes[]}` / 列表 / 撤销）；令牌 `lc_pat_<32B random>` 仅创建时返回一次，SHA-256 哈希落库（Mongo `pats` collection）。
- scope v1 仅一个：`sandbox:execute`。
- 新依赖 `authenticate_pat`（`lc_pat_` 前缀区分 JWT 路径），`last_used_at` 节流更新。
- 部署前提写入文档：`JWT_SECRET_KEY` 必须固定。

### 3.2 沙箱中继通道（SSE + POST）

- `GET /api/sandbox/channel`（PAT，scope `sandbox:execute`）：SSE 长连接。帧类型：
  - `hello`：分配 `client_id`，返回当前生效配置；
  - 注释心跳帧：每 15s（同时防中间设备空闲断连）；
  - `tool_call`：执行请求 `{call_id, op, payload, timeout}`。
- `POST /api/sandbox/results/{call_id}`：daemon 回传 `{status, stdout?, stderr?, result?, error?}`。
- **连接注册表**：Redis `sandbox:clients:{user_id}` → `{client_id: node_id, last_seen}`，TTL 35s，心跳续期；SSE 断开即摘除。同用户新连接踢旧连接（v1 只允许一个活跃 daemon，多设备场景见 §11）。
- **跨进程路由**（arq worker 跑 agent、SSE 落在 API 进程）：调用方把请求写入 Redis list `sandbox:req:{user_id}` 并 async 等待结果 key（TTL 120s）；持有连接的进程 BLPOP 转发、收到 POST 结果后写回。在线检查：注册表无条目 → 立即 `ErrorCode.DAEMON_OFFLINE`，不入队。

### 3.3 LocalSandboxBackend

- 实现 `src/infra/sandbox/` 既有后端接口，成为 E2B/Daytona/Cube 的平级选项。
- 能力：`exec(code|cmd, timeout)`、文件 `read/write/list`（限 roots）、产物回传（v1 单文件 ≤2MB 内嵌 base64，更大见 §11）。
- 超时语义：下发后 30s 无 daemon ACK → `SANDBOX_TIMEOUT`；exec 总超时默认 120s（可配）。

### 3.4 会话级沙箱路由

- session `metadata.agent_options.sandbox: "cloud"（默认） | "local"`。
- agent 装载沙箱/文件工具时据此选择后端；`local` 且离线时报错（或按配置回退 cloud，默认关）。
- 前端会话创建/设置处可切换，存量会话不受影响。

### 3.5 确认机制（复用 HITL）

- 本地 `write/edit/exec` 默认先触发 `ask_human` 中断（deepagents interrupt），网页端弹窗确认后才经中继下发 daemon；确认策略三档：全部确认（默认）/仅命令确认/免确认。
- 实现注意：确认发生在服务端工具内部 interrupt，daemon 只收到已确认的执行请求。

### 3.6 错误码与 i18n

新增 `ErrorCode`：`DAEMON_OFFLINE`、`SANDBOX_TIMEOUT`、`SANDBOX_PAYLOAD_TOO_LARGE`、`PAT_NOT_FOUND`、`PAT_SCOPE_DENIED`、`PAT_EXPIRED` 等；五语 i18n 同步（`scripts/sync_error_locales.py`），CI 强制覆盖。

## 4. 本地 daemon（新顶层目录 `client/`，同一 uv 工程）

```
client/lambchat_sandbox/
├── transport/   # SSE 客户端（重连指数退避，首试 1s）+ 结果 POST
├── executor/    # 子进程执行：cwd 限 roots 内会话工作目录、进程组、超时 kill、
│                #   stdout/stderr 各截断 256KB
├── fsops/       # 文件读写：resolve() 后必须在 roots 内（防符号链接逃逸）、
│                #   读上限 2MB/文件、二进制检测
├── audit.py     # 每会话 JSONL 审计（命令、写操作、结果摘要）
├── auth.py      # PAT 存 OS keyring
├── config.py    # ~/.lambchat/sandbox.json（server_url、roots、确认策略）
└── cli.py       # 前台运行入口（调试）
```

## 5. Tauri 壳集成（M3）

- `tauri.conf.json` 增 `externalBin: lambchat-sandbox-<target_triple>`（PyInstaller 产物）；`tauri-plugin-shell` 启停；健康检查失败自动重启（3 次后托盘提示）。
- 托盘菜单：在线状态 / roots 列表 / 版本 / 打开日志目录。
- 首次配对向导：壳内登录 → 创建 PAT（仅 `sandbox:execute`）→ 写入 keyring → 连接状态绿灯。
- 网页端（无桌面端浏览器）会话的"本地沙箱"选项置灰并引导安装桌面端。

## 6. 前端（M3）

- 会话沙箱选择器：云端/本地 + daemon 在线状态点（轮询 `GET /api/sandbox/status`，10s 间隔；不依赖 WebSocket，后续可优化为通知推送）。
- 设置页「本地沙箱」分区：连接状态、roots 管理、确认策略、离线回退开关。
- 本地文件/命令工具做专属 Item（遵循 `themedToolItems` 配色约定与现有 Item 模式；`client/` 不在 CI 扫描范围，自愿遵循）。
- 全部文案 zh/en/ja/ko/ru 五语。

## 7. 安全模型

1. 单向出网：仅 daemon→服务端 SSE/POST，服务端永不向客户端发起连接。
2. PAT：单 scope、哈希落库、可撤销、可过期；daemon 仅执行所属用户自己会话下发的请求。
3. 软隔离如实标注：子进程 + roots 目录边界，非容器隔离；危险操作默认 HITL 确认；本地审计日志可追溯。
4. 隐私边界（同 §1 声明）：文件内容/代码/执行结果流经服务端。

## 8. 测试策略（全 TDD）

- 服务端 pytest：SSE 通道（帧序列、心跳过期、注册表 TTL、踢旧连）；跨进程路由（Redis 请求/结果往返、ACK 超时）；Backend（离线 fail-fast、exec 超时、payload 上限，daemon 用 mock）；会话路由；PAT 生命周期；确认 interrupt 流程。
- daemon pytest：路径逃逸拦截（含符号链接）、读上限/二进制、子进程超时与输出截断、重连、审计写入。
- 前端 vitest：选择器/状态/设置逻辑、错误码五语覆盖（CI 强制）。
- 端到端：staging（`update-staging.sh`）真机跑"网页选本地沙箱 → 本地文件问答 + 代码执行 → 结果回显"。

## 9. 分发（M4）

- 扩 `app-release.yml`：PyInstaller 三平台矩阵（win-x64 / macos-arm64+x64 / linux-x64），daemon 随壳成对发布（版本必须匹配）。
- 签名/公证证书：开放问题（同 v1），可先无签名发布并文档标注。

## 10. 里程碑（每步独立可合入 develop）

1. **M1 服务端**：PAT + SSE 通道 + Redis 路由 + LocalSandboxBackend（mock daemon 全测）+ 会话沙箱路由。
2. **M2 daemon 闭环**：CLI 形态 daemon，网页端选"本地沙箱"真机跑通文件问答与代码执行。
3. **M3 Tauri 集成**：sidecar + 托盘 + 首次配对 + 会话选择器/设置页/状态 UI。
4. **M4 分发**：打包矩阵、签名决策、文档。

## 11. 风险与开放问题

| 项 | 说明 | 缓解 |
|---|---|---|
| SSE 经企业代理被缓冲/空闲断连 | 非常规部署环境可能出现 | 15s 心跳注释帧防空闲断连；k8s ingress SSE 配置已有生产验证；daemon 自动重连 |
| 跨进程路由延迟 | BLPOP 转发 + Redis 往返 | 预期 <100ms，M1 用集成测试实测兜底 |
| 多设备同账号 | v1 后连踢前连，一次只有一个活跃 daemon | 文档明确；按会话绑定指定设备列为后续增强 |
| 大文件/产物回传 | v1 限 2MB 内嵌 | 更大走分片通道（后续迭代） |
| 长任务 | 超过超时上限即失败 | 上限可配；v1 不支持超长任务，UI 提示拆分 |
| 子进程软隔离 | 非硬隔离，恶意/失控代码理论可逃逸 roots | HITL 确认默认开 + 审计；Docker 后端作为后续硬隔离选项 |
| 签名证书 | 产品化分发需要 | 开放问题，M4 前决策 |

## 12. 业界对标与形态依据（2026-09 调研）

调研范围：OpenAI Codex（Local/Cloud）、Claude Code（--cloud/--teleport/Remote Control）、Claude Desktop MCP、Cursor（CLI/Cloud Agents/handoff）、Gemini CLI、Devin（默认云/Outposts）。三种主流模式：

- **A. 本地 agent**（Codex CLI、Gemini CLI、Claude Code、Cursor CLI）：agent 循环与执行全在本机，是独立产品面，能力自成一体，与网页端存在差距（各厂商均接受此差距）。同步到网页均为部分实现：Codex 靠 relay 同步活跃会话（双向历史至今 open issue #21079/#5609），Claude Code 只有单向快照交接，Gemini CLI 干脆无同步。
- **B. 云 agent**（Codex Cloud、Cursor Cloud、Devin 默认、Claude Code web）：全部在厂商 VM 执行。LambChat 现状（服务端 agent + E2B/Daytona）即此模式。
- **C. 云 brain + 本机执行**（**Devin Outposts**、Claude Desktop MCP）：agent 决策在云端，执行在用户机器；网络均为"机器仅出网拨号、零入站"。**本设计 v2 与 Devin Outposts 同构**（其每个 session 配 OpenShell 沙箱，对应我们的子进程+roots+确认）；Claude Desktop MCP 的 Fileserver 目录白名单对应我们的 roots。

**选型结论**：本项目需求是"给现有平台加本地执行能力"而非"做独立终端产品"，逐字对应模式 C；模式 A（本地 agent + 网关 + ingest 同步，即被否的 v1）作为未来"本地 CLI 入口"可选项保留，与 v2 共享 `client/`、PAT 与打包管线，不互斥。Cursor 的本地↔云 seamless handoff 列为 v2 落地后的演进方向（对应本设计的"离线回退云端"开关的推广）。
