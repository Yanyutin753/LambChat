# 插件中心（Plugin Hub）设计：技能 / MCP / 角色统一插件体系

日期：2026-09-13
状态：已实现（feat/plugin-hub）

## 背景与目标

LambChat 现有三套相互独立的扩展资源：

| 资源 | 存储 | 作用域 | 角色绑定 |
|---|---|---|---|
| 技能 | `skill_files` + `skill_marketplace` | 用户级（商店为发布区） | persona `skill_names` 白名单 |
| MCP | `system_mcp_servers` / `user_mcp_servers` | 平台级 + 用户级 | 无 |
| 角色 | `persona_presets` | 用户/全局 | 绑技能，不绑 MCP |

参考 OpenAI Codex 的插件模型（单 manifest 多资源：一个插件声明 skills + mcpServers + hooks，经 marketplace 安装，运行时按 tier 合并）与本仓库衍生的 PluginPocket（HTTP MCP 插件 / Agent Skill / 装备组），将三者收敛为统一的「平台插件」体系：

1. **插件 = 能力包**：一个插件可同时携带多个技能、多个 MCP server 声明、一个可选的角色预设。
2. **平台绑定**：插件一律上架平台商店（`plugins` collection），管理员上架/激活，保留用户投稿通道（admin 激活后可见），安装来源统一记平台。
3. **角色升级**：persona 可绑定插件（一键获得技能 + MCP），也可单独白名单 MCP server；角色预设本身可作为插件负载发布，安装即得。
4. **零破坏迁移**：旧商店技能启动时幂等迁移为单技能插件；旧 API、旧数据、已安装技能全部继续工作。

## 核心决策

### 数据模型

新 collection（`src/infra/plugin/`）：

- `plugins`：插件元数据 + 负载声明。字段：`name`(unique)、`display_name`、`description`、`version`、`author_name`、`tags[]`、`skills[]`（每项 `{skill_name, description, tags}`）、`mcp_servers[]`（每项 `{name, transport, url, headers(密文), ref: bool}`，`ref=true` 表示引用既有平台 server）、`persona`（可选 `{name, description, avatar, tags, system_prompt, starter_prompts}`）、`status`(draft/active/deactivated)、`created_by`、`install_count`、`migrated_from`。
- `plugin_files`：技能负载文件，`(plugin_name, skill_name, file_path)` unique，结构对齐 `skill_marketplace_files`。
- `plugin_installs`：`(user_id, plugin_name)` unique，记录安装版本与时间。

权限复用 `marketplace:read / publish / admin` 三档（语义即"商店"），避免既有角色迁移。

### MCP 物化（平台治理优先）

插件激活（admin `PATCH /{name}/activate`）时：

- inline 配置 → `MCPStorage.create_system_server` 物化为平台级 server，附 `source_plugin` 标记，自动继承平台加密、`allowed_roles`、配额治理；
- `ref` 引用 → 仅校验目标 system server 存在；
- server 名冲突（已被其他插件/手工占用）→ 激活失败并报 `plugin_mcp_name_conflict`。
- 停用插件 → 物化 server 置 `enabled=false`（可逆，不删除）；删除插件 → 物化 server 一并删除。

`SystemMCPServer` / `MCPServerResponse` 增加 `source_plugin: Optional[str]`，前端 MCP 面板展示「来自插件」徽标。

### 安装语义

`POST /api/plugins/{name}/install`（插件须 active）：

- 技能负载 → `SkillStorage.sync_skill_files` 落用户 `skill_files`，`__meta__.installed_from = "plugin"`（`InstalledFrom` 新增值）；
- MCP → 安装时无需动作（激活时已物化为平台 server，用户按平台规则可见可用）；
- 角色负载 → 复制为用户私有 persona 草稿（对齐 `copy_preset` 行为）；
- 卸载 → 删 `plugin_installs` 记录；技能/角色副本由用户在既有面板管理（与旧商店语义一致）。

### Persona 绑定

`PersonaPreset` 新增 `plugin_names: list[str]` 与 `mcp_server_names: list[str]`：

- `use_preset` 生成快照时：`plugin_names` 展开为插件技能名并入 `skill_names` 求交集（缺失插件记 `missing_plugin_names`）；绑定插件的物化 server 名并入 `mcp_server_names`；
- 快照透传 `mcp_server_names`，`resolve_persona_request` 将其设为请求级 `enabled_mcp_servers` 白名单。

### 运行时白名单（复用 disabled_mcp_tools 通道）

`AgentRequest.enabled_mcp_servers: Optional[list[str]]`，与 `disabled_mcp_tools` 同路径穿透：chat 路由 → `agent.stream` kwargs → `configurable` → fast/search/team agent context。context 在 MCP 工具懒加载后新增 `filter_mcp_tools_by_server_whitelist` 过滤：仅按「可归属 server」（`server:tool` 前缀或 `tool.server` 属性）过滤，无法归属的工具保留，不影响内置工具与内部虚拟 server。

### 旧数据迁移（幂等，启动时）

`init_plugin_indexes()` 注册进 `startup_indexes.py`，与 `init_skill_indexes()` 并列：

- 遍历 `skill_marketplace`，`plugins` 中无同名文档则创建单技能插件（status 对齐 `is_active`，保留 `created_by`，`migrated_from: "skill_marketplace"`），并复制 `skill_marketplace_files` → `plugin_files`；
- 原集合只读保留，不做删除或改写；旧 `/api/marketplace`、`/api/skills` 全部不动。

## API（`/api/plugins`，`src/api/routes/plugin.py`）

用户（`marketplace:read`）：`GET /`（active 列表，search/tags/分页）、`GET /tags`、`GET /installed`、`GET /{name}`、`GET /{name}/skills/{skill}/files`、`GET /{name}/skills/{skill}/files/{path}`、`POST /{name}/install`、`POST /{name}/update`、`DELETE /{name}`（卸载）。

投稿/管理（`marketplace:publish` / `marketplace:admin`）：`POST /`（创建，admin 可直接 active，普通投稿为 draft）、`PUT /{name}`（创建者或 admin，版本自增）、`PATCH /{name}/activate`（admin，含 MCP 物化/停用）、`DELETE /{name}`（admin 或 draft 创建者，含物化 server 清理）。

错误码走 `ErrorCode`（`plugin_not_found`、`plugin_inactive`、`plugin_already_installed`、`plugin_name_exists`、`plugin_mcp_name_conflict`、`plugin_invalid_payload`、`plugin_not_installed`），五语 i18n 同步 `backendErrors.*`。

## 前端

- **插件中心**：`SkillsHubPanel` 的 marketplace tab 升级为 plugins tab（路由 `/plugins`），新 `PluginMarketPanel`（对齐旧 `MarketplacePanel` 结构：卡片网格 + 搜索/标签过滤 + 安装确认 + 预览 Modal + admin 激活/删除 + 创建侧栏 `PluginFormSidebar`）。插件卡展示能力徽标（N 技能 / N MCP / 含角色）。
- **Persona 编辑器**：新增 `PersonaEditorPluginSelector`（已安装插件多选）与 `PersonaEditorMcpSelector`（可见 MCP server 多选），复用 `SkillSelector` 的交互与样式模式。
- **MCP 面板**：system server 卡片在 `source_plugin` 存在时展示「来自插件」徽标。
- 全部新文案进 zh / en / ja / ko / ru 五个 locale。

## 测试

- 后端：`tests/infra/plugin/`（storage CRUD/安装/物化/迁移幂等）、`tests/api/test_plugin_routes.py`、persona 绑定（use_preset 展开）、`enabled_mcp_servers` 穿透（镜像 disabled_skills 传播测试）、tool_filter 白名单单测。
- 前端：`pluginApi` 单测、Hub state 纯函数测试更新、相关 Source 结构测试。

## 明确不做（YAGNI）

- 不引入插件间依赖、外部 marketplace 源（git/npm）、插件热重载——平台商店为唯一来源。
- 不改动 RBAC 角色权限体系（复用 marketplace 三档权限）。
- 不迁移/重写用户已安装技能与旧商店 API。
