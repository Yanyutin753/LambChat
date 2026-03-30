# mcporter 沙箱 MCP 集成方案

## Context

当前 LambChat 的 MCP 系统仅支持外部 HTTP/SSE 服务器（通过 `langchain-mcp-adapters` 连接）。用户希望：
1. 在沙箱内运行 MCP 服务器（stdio 类型），通过 mcporter 管理
2. 用户输入命令（如 `npx -y firecrawl-mcp`），Agent 自动在沙箱内安装、配置、调用
3. 沙箱 MCP 与外部 MCP 在前端同一面板显示

## 方案概览

新增 `sandbox` 传输类型，复用现有 MCP 存储层（MongoDB），在沙箱内通过 mcporter CLI 管理生命周期。Agent 通过 `execute()` 调用 mcporter 命令操作沙箱内 MCP。

### 架构

```
用户添加 "sandbox" 类型 MCP（command: "npx -y firecrawl-mcp"）
  → 存入 MongoDB（transport=sandbox, command=..., env_keys=[...]）
  → 前端 MCPPanel 显示（badge: "Sandbox"）
  → Agent 发现 sandbox 类型 MCP → 注入专用工具
  → 工具内部：sandbox.execute("mcporter call server.tool arg=val")
  → mcporter 在沙箱内启动 stdio MCP server，调用工具，返回结果
```

## 新建文件

### 1. `src/infra/tool/sandbox_mcp_tool.py` — Agent 工具

沙箱 MCP 管理工具，当沙箱内存在 `transport=sandbox` 的 MCP 服务器时注入到 Agent。

- `manage_sandbox_mcp(action, server_name?, command?, tool_name?, arguments?)` — 统一工具
  - `action="add"`: 在沙箱内安装并注册 MCP 服务器
    - 执行 `mcporter config add <name> --stdio "<command>"`
    - 注入用户环境变量（通过 `--env KEY=$KEY`）
    - 执行 `mcporter list <name> --json` 获取工具列表
    - 返回可用工具列表给 Agent
  - `action="list"`: 列出沙箱内所有 MCP 服务器的工具
    - 执行 `mcporter list --json`
    - 解析输出返回工具清单
  - `action="call"`: 调用沙箱内 MCP 工具
    - 执行 `mcporter call <server>.<tool> <args> --output json`
    - 解析并返回结果
  - `action="remove"`: 移除沙箱内 MCP 服务器
    - 执行 `mcporter config remove <name>`

- 通过 `ToolRuntime` 获取 sandbox backend，调用 `backend.aexecute()`

### 2. `src/infra/mcp/sandbox_discovery.py` — 沙箱 MCP 工具发现

独立的发现模块，在 Agent 初始化时：
1. 从 MongoDB 加载 `transport=sandbox` 的 MCP 配置
2. 确保沙箱已启动
3. 调用 `mcporter list --json` 发现实际可用工具
4. 返回工具列表（用于前端展示和 Agent 上下文）

## 修改文件

### 3. `scripts/create_e2b_template.py` — 安装 mcporter

在 E2B 模板构建脚本中添加：
```python
# 安装 Node.js + mcporter
template = template.run_cmd("curl -fsSL https://bun.sh/install | bash")
template = template.run_cmd("~/.bun/bin/bun install -g mcporter")
```
同时在 `SYSTEM_PACKAGES` 中不需要额外系统包（Bun 自包含）。

### 4. `src/kernel/schemas/mcp.py` — 扩展传输类型

- `MCPTransport` 添加 `SANDBOX = "sandbox"`
- `MCPServerBase` 添加 sandbox 专用字段：
  ```python
  command: Optional[str] = Field(None, description="stdio 命令（sandbox 传输）")
  env_keys: Optional[list[str]] = Field(None, description="需要注入的环境变量 key 列表")
  ```
- `MCPServerCreate` / `MCPServerUpdate` 同步添加这些字段
- 添加校验：sandbox 类型必须提供 `command`

### 5. `src/kernel/types.py` — 添加权限

```python
MCP_WRITE_SANDBOX = "mcp:write_sandbox"
```

### 6. `src/kernel/schemas/permission.py` — 权限元数据

- `PERMISSION_METADATA` 添加 `mcp:write_sandbox` 的中文标签
- `PERMISSION_GROUPS_CONFIG` 的 MCP 分组中添加该权限

### 7. `src/infra/mcp/storage.py` — 支持 sandbox 字段

- `_doc_to_system_server()` / `_doc_to_user_server()` / `_doc_to_response()` 处理 `command` 和 `env_keys` 字段
- `_doc_to_config_dict()` 对 sandbox 类型返回 `{transport: "sandbox", command: ..., env_keys: ...}`
- `import_servers()` 支持 sandbox 类型导入
- 新增 `get_sandbox_servers(user_id)` 方法 — 返回用户所有 sandbox 类型 MCP

### 8. `src/infra/tool/mcp_client.py` — sandbox 传输处理

`_create_mcp_client()` 中对 `sandbox` 类型的服务器**跳过外部连接**（由沙箱内 mcporter 处理），不创建 `langchain-mcp-adapters` 连接。

### 9. `src/api/routes/mcp.py` — 路由更新

- `_has_permission_for_transport()` 添加 sandbox 类型判断
- `discover_server_tools()` 对 sandbox 类型：调用 `sandbox_discovery.py` 在沙箱内执行 `mcporter list --json` 获取工具

### 10. `src/agents/search_agent/context.py` — 注入 sandbox MCP 工具

在 `setup()` 中，当 `ENABLE_SANDBOX` 且用户有 sandbox 类型 MCP 时：
```python
if settings.ENABLE_SANDBOX:
    sandbox_mcp_servers = await self._load_sandbox_mcp_configs()
    if sandbox_mcp_servers:
        self.tools.append(get_sandbox_mcp_tool(sandbox_mcp_servers))
```

### 11. `src/agents/fast_agent/context.py` — 同上

SearchAgent 和 FastAgent 都可能需要 sandbox MCP（如果启用了沙箱）。

### 前端文件

### 12. `frontend/src/types/mcp.ts` — 类型扩展

- `MCPTransport` 添加 `"sandbox"`
- `MCPServerBase` 添加 `command?: string`, `env_keys?: string[]`
- `MCPServerCreate` / `MCPServerUpdate` 同步

### 13. `frontend/src/components/mcp/MCPServerCard.tsx` — 显示 sandbox

- `TRANSPORT_LABELS` 添加 `sandbox: "Sandbox"`（蓝色 badge）
- `TRANSPORT_COLORS` 添加 sandbox 配色
- sandbox 类型显示 `command` 而非 `url`
- 显示 `env_keys` 标签（提示哪些环境变量会被注入）

### 14. `frontend/src/components/mcp/MCPServerForm.tsx` — 表单支持

- 添加 sandbox 传输选项（需要 `mcp:write_sandbox` 权限）
- 选择 sandbox 时：
  - 显示 `command` 输入框（如 `npx -y firecrawl-mcp`）
  - 显示 `env_keys` 多选/输入（提示用户哪些环境变量需要注入）
  - 隐藏 `url` 和 `headers` 字段
  - 提示信息：需要先在"环境变量"中配置对应的 API Key

### 15. `frontend/src/i18n/locales/zh.json` + `en.json` — 国际化

添加 sandbox 相关翻译：
- `mcp.form.transportSandbox` / `mcp.form.command` / `mcp.form.commandPlaceholder`
- `mcp.form.envKeys` / `mcp.form.envKeysPlaceholder` / `mcp.form.envKeysHint`

## 关键设计决策

1. **不替换现有 MCP 系统**：sandbox MCP 与外部 SSE/HTTP MCP 并存，各走各的通道
2. **Agent 统一工具**：用一个 `manage_sandbox_mcp` 工具处理所有操作，避免工具膨胀
3. **环境变量桥接**：sandbox MCP 的 `env_keys` 引用用户在"环境变量"中已存的 key，沙箱已有这些变量，mcporter 命令通过 `$KEY` 引用
4. **工具发现走 API**：前端的"发现工具"按钮调用后端 API，后端在沙箱内执行 `mcporter list`，结果返回前端
5. **持久化在 MongoDB**：sandbox MCP 配置存在 MongoDB（和外部 MCP 一样的集合），重建沙箱时自动重装

## 实现顺序

1. `types.py` → 添加权限枚举
2. `permission.py` → 添加权限元数据
3. `schemas/mcp.py` → 扩展传输类型和字段
4. `infra/mcp/storage.py` → 支持 sandbox 字段存取
5. `api/routes/mcp.py` → 权限和路由更新
6. `scripts/create_e2b_template.py` → 安装 Bun + mcporter
7. `infra/tool/sandbox_mcp_tool.py` → Agent 工具实现
8. `infra/tool/mcp_client.py` → 跳过 sandbox 类型
9. `agents/*/context.py` → 注入 sandbox MCP 工具
10. 前端类型 + 表单 + 卡片 + 国际化

## 验证方式

1. 创建 sandbox 类型 MCP 服务器（command: `npx -y @anthropic/mcp-server-fetch`）
2. 前端 MCPPanel 显示蓝色 "Sandbox" badge
3. 点击"发现工具"按钮，沙箱内安装并返回工具列表
4. Agent 会话中可调用沙箱内 MCP 工具
5. 环境变量（如 `FIRECRAWL_API_KEY`）通过 `env_keys` 正确注入
