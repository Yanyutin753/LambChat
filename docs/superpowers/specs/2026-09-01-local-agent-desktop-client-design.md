# LambChat 本地 Agent 桌面客户端设计

- 日期：2026-09-01
- 状态：待评审
- 分支：`feat/local-agent-desktop`（自 `develop` 拉出）

## 0. 决策记录

| 决策点 | 结论 | 备注 |
|---|---|---|
| 范围 | 全量一期做完（agent 内核 + 服务端打通 + 桌面端 + 分发） | 不分期砍范围，按里程碑顺序交付 |
| 仓库形态 | **不开新仓库**，LambChat monorepo 新顶层目录 `client/` | 前端/deepagents 依赖/事件契约/CI 同仓复用 |
| 使用范围 | **分发给所有 LambChat 用户**（产品化） | 安装包、updater、每用户 token 流程都要做 |
| 模型打通 | **服务端网关**，模型 key 全程不出服务端 | 本地 agent 拿 PAT 调网关 |
| 网关协议 | **OpenAI Responses API**（`/v1/responses`） | 用户指定；LambChat LLM 层已有 `/v1/responses` 线格式经验（`src/infra/llm/client.py:77-87,586`） |
| 本地会话呈现 | 预留伪 `agent_id="local"`，混排进现有会话列表 + 徽标 | `POST /api/sessions` 不校验 AgentFactory 注册表（`src/api/routes/session.py:189`，已核实） |

## 1. 背景与目标

LambChat 的 agent 全部在服务端执行，无法访问用户本地文件。目标是提供一个桌面客户端：agent 进程跑在用户本机、直连本地文件与数据，同时与 LambChat 平台打通——模型经服务端网关调用（配置与 key 留在服务端），对话回传 LambChat 存储并在现有 Web/桌面界面查看。

**非目标（v1 明确不做）**：服务端反向回调客户端；本地 agent 复用服务端工具生态（memory/skill/MCP/沙箱/arq 定时任务）；网关有状态存储（`previous_response_id` / `GET /responses/{id}`）；移动端（Capacitor）本地模式。

## 2. 总体架构

```
┌────────────────────── 用户机器 ──────────────────────┐
│  Tauri 桌面壳（复用 frontend/ 同一套 SPA）            │
│   ├ 远程模式：直连 LambChat API（现状不动）            │
│   └ 本地模式：提交到本地 daemon（127.0.0.1:随机端口）  │
│  本地 agent daemon（Python 二进制，随壳 sidecar 分发） │
│   ├ deepagents 图 + 本地文件工具（FilesystemMiddleware）│
│   ├ LLM ──────► LambChat 网关（PAT，Responses API）   │
│   └ 每轮结束 ──► ingest 端点（回传 completed trace）   │
└──────────────────────────────────────────────────────┘
        只有客户端→服务端单向 HTTPS；服务端永不回调客户端
```

核心原则：

1. **本地 agent 运行时不 import 服务端任何代码**（`src/`），打通全靠两个 API：网关 + ingest。
2. **代码复用靠同仓**：deepagents/langchain 是既有依赖；trace 事件契约、前端、CI、发版管线同仓演进。
3. **消息查看零改动**：Web 端消息 = traces 事件流，本地会话以标准事件序列落库后，现有历史/实时读取路径直接可用。

## 3. 服务端新增（M1，三件套）

### 3.1 PAT 个人访问令牌

客户端是分布式产品，不能存用户密码，JWT（access 24h / refresh 7d）对常驻客户端不友好，新增 PAT：

- 端点：`POST /api/auth/pat`（创建，body：`{name, scopes[], expires_at?}`）、`GET /api/auth/pat`（列表，仅元数据）、`DELETE /api/auth/pat/{pat_id}`（撤销）。
- 令牌形如 `lc_pat_<32B random>`，**仅在创建时返回一次**；库中存 SHA-256 哈希（Mongo 新 collection `pats`：`{pat_id, user_id, name, scopes, token_hash, prefix, created_at, expires_at, last_used_at, revoked}`）。
- scope 枚举 v1：`gateway:invoke`、`chat:import`。
- 鉴权：新增依赖 `authenticate_pat`，解析 `Authorization: Bearer lc_pat_*` → 查哈希 → 绑定用户 + scope 校验；`last_used_at` 节流更新（≥5min 一次）。普通 JWT 路径不受影响（`lc_pat_` 前缀区分）。
- 部署前提（写入文档 & `.env.example`）：`JWT_SECRET_KEY` 必须固定，否则重启后既有 JWT 全失效。
- 错误处理走 `src/kernel/errors.py` 的 `ErrorCode`（新增 `PAT_NOT_FOUND`、`PAT_SCOPE_DENIED` 等），i18n 五语同步（`scripts/sync_error_locales.py`）。

### 3.2 模型网关（Responses API）

- 路由：`POST /api/gateway/v1/responses`（新文件 `src/api/routes/gateway.py`）。
- 鉴权：PAT（scope `gateway:invoke`）或等价权限的 JWT；新 RBAC 权限 `gateway:invoke`（管理员角色默认授予，普通角色按需开）。
- 请求：Responses API 形状。v1 支持子集：`{model, input: str | ResponseInputItem[], instructions?, tools?（function）, tool_choice?, stream?, temperature?, max_output_tokens?, reasoning?}`；不支持 `previous_response_id`、`store`、`background` 等有状态/异步参数，传入即返回 `ErrorCode.GATEWAY_PARAM_UNSUPPORTED`。
- `model` 字段 = LambChat 模型配置的 model_id（或唯一 name 别名）；解析复用 `LLMClient.get_model()`（`src/infra/llm/client.py:628`）。
- 内部转换：input items（含 `function_call` / `function_call_output`）→ LangChain messages → 调用模型 → 流式 chunk 转回 Responses SSE 事件（`response.created`、`response.output_item.added`、`response.output_text.delta`、`response.output_item.done`、`response.completed` 含 usage；工具调用产出 `function_call` output item）。非流式返回完整 Response JSON。转换经验参考 `src/infra/llm/openai_chat.py` 既有 `/v1/responses` 线格式处理。
- **无状态**：`response.id` 每次新生成，不落库、不可回查；对话状态由调用方（本地 agent）维护。
- 用量记账：从 LangChain `usage_metadata` 提取，写入现有 `src/infra/usage/` 存储（按 PAT 所属用户 + 模型记账），保证配额/统计口径一致。
- 限流：进程内每用户令牌桶（请求/分钟，配置项 `GATEWAY_RATE_LIMIT_PER_MIN`，默认 60）。多 worker 部署下为近似值，v1 接受并记录于文档。
- 敏感路径（模型 key 代理）：保守实现，禁止路由层 `HTTPException`，全量测试覆盖（见 §8）。

### 3.3 消息 ingest 端点

- 路由：`POST /api/sessions/{session_id}/messages/import`。
- 鉴权：PAT（scope `chat:import`）或 JWT；会话所有权校验与现有路由一致。
- 请求体：`{run_id?, agent_id?("local"), status?("completed"|"error"), schema_version?, events: [{event_type, data, timestamp?}]}`（`schema_version` 为契约版本预留字段，v1 可省略，默认当前版本）。允许的事件类型白名单：`user:message`、`message:chunk`、`thinking`、`tool:start`、`tool:result`、`artifact:result`、`token:usage`、`done`、`error`；服务端分配 `seq`，逐条经 **DualEventWriter** 写入（禁止绕过——事件分片有 seq/chunk lease 机制），最后 `complete_trace` 置终态并更新 session `current_run_id` 与未读数。
- **幂等**：携带 `run_id` 重试时，若该 run 已导入，返回 `ErrorCode.RUN_ALREADY_IMPORTED`（不重复写入），本地离线重试安全。
- 终态约束：trace 必须 `completed`/`error`，否则历史读取（`completed_only=True`，`src/infra/session/dual_writer.py:790`）不可见。
- 附件：v1 仅允许引用服务端已有 upload key（`data.attachments[].key` 校验存在且属于该用户）；本地文件内容以文本预览内联，不经 ingest 上传文件。
- 单次事件数上限（默认 2000）与体积上限（2MB），超限返回 `ErrorCode.IMPORT_PAYLOAD_TOO_LARGE`。

## 4. 本地 agent（新顶层目录 `client/`）

### 4.1 目录结构（同一 uv 工程）

```
client/
├── lambchat_client/
│   ├── agent/     # deepagents 图组装、系统提示词
│   ├── tools/     # local_run_command、ask_user（文件工具走 FilesystemMiddleware）
│   ├── gateway/   # ChatOpenAI(base_url=网关, use_responses_api=True) 封装
│   ├── sync/      # 内部事件 → LambChat trace 事件映射 + ingest 上传（磁盘队列，指数退避重试）
│   ├── daemon/    # 本地 HTTP 服务（FastAPI），API 镜像 LambChat chat 协议
│   ├── auth/      # PAT 存 OS keyring（keyring 库）
│   ├── config.py  # ~/.lambchat/client.json（server_url、roots、确认策略）
│   └── cli.py     # CLI 入口（调试与无 GUI 使用）
└── tests/         # 镜像结构
```

### 4.2 agent 运行时与工具

- 图组装：`create_deep_agent(tools=[local_run_command, ask_user])` + **FilesystemMiddleware**（deepagents 既有机制）让内置 `ls/read_file/write_file/edit_file/glob/grep` 直连真实磁盘，路径限定在用户配置的根目录集合内。
- 路径安全：每次操作 `Path.resolve()` 后必须仍位于 roots 内（防符号链接逃逸）；读文件有大小上限（默认 2MB/文件）与二进制检测。
- `local_run_command`：执行任意 shell 命令，**必须经 `ask_user` 确认**（白名单命令可配置免确认）。
- 写入确认策略：默认策略下 `write_file`/`edit_file` **经 `ask_user` 确认**后执行；用户可在设置中放开为"roots 内直接写"（效率模式）。命令一律确认，不受放开影响。
- `ask_user`：deepagents interrupt 机制，daemon 转发确认请求到壳（复用现有 HITL 弹窗交互模式），用户响应后恢复执行。
- LLM：`langchain_openai.ChatOpenAI(base_url="{server}/api/gateway/v1", api_key=PAT, use_responses_api=True)`；工具 schema 经 Responses `tools` 通道传递。
- 本地审计：每会话写本地 JSONL 审计日志（文件操作、命令、确认结果）。

### 4.3 daemon 协议（镜像 LambChat chat 协议）

绑定 `127.0.0.1` 随机端口，启动时生成一次性本地 token，仅壳持有。端点：

- `POST /api/chat/stream`：提交消息，返回 `{session_id, run_id, trace_id, status}`（与 LambChat 同构）。
- `GET /api/chat/sessions/{id}/stream?run_id=`：SSE，**直接产出 LambChat 事件格式**（`message:chunk`/`thinking`/`tool:start`/`tool:result`/`done`…），前端事件处理器零适配。
- `POST /api/chat/cancel`；HITL 响应端点（ask_user 应答）。
- `GET /api/health`、`GET /api/local/config`（roots、确认策略、网关连通状态）。

会话模型：daemon 维护本地会话注册表，每个本地会话先经服务端 `POST /api/sessions`（`agent_id="local"`）建档，本地状态与服务端 session_id 一一对应。

### 4.4 回传与离线策略

- **每轮结束一次性 ingest**：服务端历史读取本就 `completed_only`，逐事件实时回传无收益且绕不开 running trace 不可见的坑；本地实时性由 daemon SSE 提供，远端 Web 界面在每轮完成后可见。
- 断网/失败：轮次事件落本地磁盘队列，指数退避重试；`run_id` 幂等保证不重不漏。

### 4.5 CLI

`python -m lambchat_client` 提供终端对话入口（同一 agent 内核，终端内 ask_user 直接 stdin 确认），用于调试与无 GUI 场景，几乎零额外成本。

## 5. Tauri 壳与前端（M3）

- sidecar：`tauri.conf.json` 增加 `externalBin: lambchat-agent-<target_triple>`（PyInstaller 产物）；`tauri-plugin-shell` 启停，daemon 以 `--port 0 --auth-token <random>` 启动，端口经 stdout 协议回传，invoke 注入 webview；退出时随壳终止；健康检查失败自动重启（3 次后提示）。
- 前端传输层抽象：`useAgent` 抽出 `ChatTransport` 接口（`submit/openStream/cancel`），现有远程实现收敛为 `RemoteTransport`，新增 `LocalTransport`（指向 daemon）；Tauri 环境下自动可用本地模式，Web 环境隐藏入口。
- 本地会话：`agent_id === "local"` 的会话在列表打“本地”徽标（zh/en/ja/ko/ru 五语）。
- 工具展示：本地文件/命令工具按项目规矩做专属 Item（参照 `ToolSearchItem` 模式与 themedToolItems 配色约定；`client/` 不在 CI 扫描范围，属自愿遵循）。
- 设置页新增“本地 Agent”分区：daemon 状态、根目录管理、命令确认策略、PAT 连接状态。

## 6. 安全模型

1. 单向出网：服务端永不回调客户端，无隧道、无反向连接。
2. 模型 key 全程留在服务端，网关是唯一出口。
3. PAT：哈希落库、scope 收窄、可撤销、可设过期；客户端存 OS keyring。
4. 本地文件边界：根目录集合 + resolve 校验；默认策略下写文件与执行命令均需 `ask_user` 确认（写确认可在设置中放开，见 §4.2）；本地审计日志可追溯。
5. daemon 仅绑定 127.0.0.1 + 每次启动随机 token，防本机其他进程劫持。
6. 网关限流 + 用量记账防滥用。

## 7. 分发与发布（M4）

- CI：扩 `app-release.yml`——构建矩阵 `windows-x64 / macos-arm64 / macos-x64 / linux-x64`，PyInstaller 打 `lambchat-agent` 单文件二进制 → Tauri externalBin 一并入包 → 现有 GitHub Releases + updater 通道升级。
- 版本：沿用 `v*` tag；壳与 sidecar 必须同版本成对发布。
- 代码签名：macOS 公证 + Windows 签名需要证书，**开放问题**（见 §10），v1 可先无签名发布并在文档标注。

## 8. 测试策略（全 TDD）

- 后端 pytest：网关协议一致性（Responses 流事件序列、工具调用往返、非流式、未知模型、PAT/scope/限流）；PAT 生命周期（创建/列表/撤销/过期）；ingest（导入后 `/api/sessions/{id}/events` 可见、幂等 409、所有权拒绝、payload 超限、trace 终态）。
- client pytest：文件工具路径逃逸拦截、大小/二进制限制、事件映射、daemon API（httpx ASGI）、离线队列重试。
- 前端 vitest：传输层选择纯函数、徽标渲染、设置分区；`backendErrorCodeCoverage.test.ts` 五语覆盖由 CI 强制。
- 验证：`make check-all`；staging（`update-staging.sh`）真机跑一轮"本地文件问答 → Web 界面可见"。

## 9. 里程碑（每步独立可合入 develop）

1. **M1 服务端三件套**：PAT → 网关 → ingest，后端独立可用（curl 可测）。
2. **M2 client 内核 + CLI**：本机闭环"本地文件问答 → LambChat 网页看到对话"。
3. **M3 daemon + sidecar + 前端本地模式**：完整桌面闭环。
4. **M4 分发工程**：打包矩阵、签名、updater、文档。

## 10. 风险与开放问题

| 项 | 说明 | 缓解 |
|---|---|---|
| `ChatOpenAI(use_responses_api=True)` + 自定义 base_url 的兼容性 | langchain-openai 对 Responses 线格式的工具调用/流事件与自定义端点的组合需要实测 | M1 末尾做一个一次性 spike 验证；有缺口则在我们网关侧补齐事件翻译，协议对外不变 |
| PyInstaller 体积与冷启动 | langchain 栈打包后约 100–200MB | 可接受；必要时换 shiv/pex |
| 多 worker 下网关限流是近似值 | 进程内令牌桶不跨进程 | v1 接受并文档化；后续可挪 Redis |
| 代码签名证书 | 产品化分发（尤其 macOS 公证）需要证书与账号 | 开放问题，等用户决策；可先无签名发布 |
| 事件契约漂移 | 本地 agent 产出的事件格式必须与服务端演进同步 | 同仓 + ingest 白名单校验；契约加版本字段（`data.schema_version`）预留 |
| deepagents 内置 `task` 子代理的文件工具行为 | 子代理继承的文件工具同样经 FilesystemMiddleware，行为一致 | M2 测试覆盖子代理场景 |
