# LambChat 插件开发文档

本文档说明 LambChat 当前的文件夹式插件开发规范。插件不是一个简单的 JSON 文件，而是一个可扩展目录：它可以声明后端能力、前端入口、插件设置、资源归属、默认数据、卸载 dry-run 策略，以及未来可继续扩展的能力。

可复制示例见 [demo/README.md](../demo/README.md) 和 [demo/demo_notes](../demo/demo_notes)。

## 设计目标

- 插件配置从全局 System Settings 中剥离，进入插件自己的 Settings 区。
- 插件启停由 Plugin Runtime 管理，不再依赖 `ENABLE_*` 全局开关。
- 插件通过 manifest 声明自己拥有的 API、工具、Agent、页面、按钮、设置、资源和默认数据。
- 插件默认数据放在插件目录内的 `plugin-data-template/`，运行时数据放在根目录 `plugin-data/{plugin_id}/`。
- 插件卸载 dry-run 可以列出资源归属和处理策略，但当前阶段不做真实删除用户数据。
- 新插件尽量只通过声明接入，不在核心代码里到处写特判。

## 推荐目录结构

```text
plugins/{install_type}/{plugin_id}/
  plugin.yaml
  backend/
    plugin.json
  frontend/
    plugin.json
  config/
    schema.json
    defaults.json
  resources/
    resources.yaml
  plugin-data-template/
    config/
      defaults.json
      current.json
    state/
      audit.jsonl
  README.md
```

当前常用安装类型：

- `plugins/system/`：系统内置插件，通常随 LambChat 启用，例如 `feedback`、`agent_team`。
- `plugins/preinstalled/`：预装插件，随仓库提供，但可默认禁用，例如 `image_generation`、`audio_transcription`。
- 后续若开放远程插件包，也应复用同样的目录结构。

## 根清单：`plugin.yaml`

`plugin.yaml` 描述插件身份、高层权限、默认启停、设置 schema 和数据模板。

```yaml
id: demo_notes
name: Demo Notes
version: 1.0.0
api_version: v1
install_type: preinstalled
entrypoint: backend
permissions:
  - demo_notes:read
  - demo_notes:write
enabled_by_default: false
settings: []
data_template: plugin-data-template
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `id` | 插件唯一 ID。建议使用小写 snake_case。 |
| `name` | 插件显示名。 |
| `version` | 插件版本。 |
| `api_version` | 插件运行时 API 版本，当前通常为 `v1`。 |
| `install_type` | 安装类型，例如 `system_builtin`、`preinstalled`。 |
| `entrypoint` | 插件入口类型，当前常用 `backend`。 |
| `permissions` | 插件声明和复用的权限集合。 |
| `enabled_by_default` | 首次加载时是否默认启用。 |
| `settings` | 插件设置 schema。没有设置也必须显式声明空列表。 |
| `data_template` | 默认数据模板目录，通常为 `plugin-data-template`。 |

## 插件设置

插件拥有的配置必须声明在插件里，不再放进全局 System Settings。

```yaml
settings:
  - key: API_KEY
    type: string
    label: pluginSettings.demo_notes.API_KEY.label
    description: pluginSettings.demo_notes.API_KEY.description
    default: ""
    sensitive: true
    required: true
    scope: system
    group: provider
    order: 10
    env_fallback: DEMO_NOTES_API_KEY
    legacy_system_setting_keys:
      - DEMO_NOTES_API_KEY
```

支持的设置类型：

- `string`
- `text`
- `number`
- `boolean`
- `select`
- `json`

规则：

- `key` 是插件局部 key，例如 `API_KEY`，不是全局 key。
- 全局唯一标识由系统组合为 `{plugin_id}.{key}`。
- 插件启停状态不放在设置里，统一交给 Plugin Runtime。
- 敏感字段 API 返回时会 mask；提交 `********` 表示保留原值。
- `env_fallback` 只用于初始导入或缺省值，不作为 UI 主数据源。
- `legacy_system_setting_keys` 用于迁移旧全局配置，并让 System Settings 隐藏旧 key。

## 后端声明：`backend/plugin.json`

后端声明用于注册 API 路由、工具、Agent 和生命周期 hook。

```json
{
  "schema": "lambchat.plugin.backend.v1",
  "plugin_id": "demo_notes",
  "backend": {
    "routes": [
      {
        "name": "demo_notes-api",
        "prefix": "/api/demo-notes",
        "module": "src.plugins.demo_notes.routes",
        "required_permissions": ["demo_notes:read", "demo_notes:write"],
        "tags": ["Demo Notes"]
      }
    ],
    "tools": [
      {
        "name": "demo_notes_create_note",
        "module": "src.plugins.demo_notes.tools",
        "required_permissions": ["demo_notes:write"],
        "legacy_ids": ["demo_notes.create_note"]
      }
    ],
    "lifespan_hooks": [
      {
        "name": "demo_notes:shutdown",
        "module": "src.plugins.demo_notes.lifecycle:close_demo_notes",
        "phase": "shutdown",
        "order": 50
      }
    ]
  }
}
```

当前可用后端贡献类型：

- `routes`：声明 FastAPI 路由挂载点。
- `tools`：声明 Agent 可调用的内部工具。
- `agents`：声明插件拥有的 Agent。
- `lifespan_hooks`：声明启动或关闭阶段 hook。

工具命名建议：

- 使用模型安全名称：字母、数字、下划线。
- 避免新工具名包含点号，例如优先 `feedback_summary`，不要 `feedback.summary`。
- 如果历史上已经有旧 id，通过 `legacy_ids` 保持兼容。
- 工具是否可暴露由插件运行态控制，不要再读 `ENABLE_*`。

## 前端声明：`frontend/plugin.json`

前端声明用于贡献页面、导航、按钮、工具渲染器、输入区选项、项目/会话/渠道/定时任务选项等 UI 能力。

```json
{
  "schema": "lambchat.plugin.frontend.v1",
  "plugin_id": "demo_notes",
  "frontend": {
    "app_tabs": [
      {
        "id": "demo_notes:notes-tab",
        "tab": "demo-notes",
        "path": "/demo-notes",
        "label": "demoNotes.nav.label",
        "panel": "demo_notes:notes-panel",
        "insert_after": "settings",
        "order": 650,
        "permissions": ["demo_notes:read"]
      }
    ],
    "app_panels": [
      {
        "id": "demo_notes:notes-panel",
        "tab": "demo-notes",
        "renderer": "demo_notes.NotesPanel"
      }
    ],
    "message_actions": [
      {
        "id": "demo_notes:save-message-note",
        "target": "assistant_message",
        "renderer": "demo_notes.SaveMessageNoteButton",
        "order": 40,
        "permissions": ["demo_notes:write"]
      }
    ],
    "i18n_namespaces": ["demo_notes"],
    "required_permissions": ["demo_notes:read"]
  }
}
```

常见前端贡献点：

- `app_tabs`：新增顶层页面或路由 tab。
- `app_panels`：把 tab 绑定到渲染器。
- `sidebar_items`：侧边栏入口。
- `user_menu_items`：用户菜单入口。
- `message_actions`：消息上的按钮，例如 Feedback 点赞/点踩。
- `tool_renderers`：工具调用结果的专属渲染。
- `chat_input_options`：聊天输入区扩展按钮。
- `chat_input_panels`：聊天输入区弹窗或选择器。
- `mention_providers`：`@` 提及候选源。
- `welcome_surfaces`：欢迎页区域。
- `assistant_identity_resolvers`：插件控制的助手身份展示。
- `agent_categories`：插件拥有的 Agent 分类。
- `project_options`、`session_options`、`channel_options`、`scheduled_task_options`：插件作用域选项。

## 插件作用域选项

当插件需要给项目、会话、渠道或定时任务保存状态时，不要新增全局字段，应该声明 scoped options。

示例：

```json
{
  "key": "SELECTED_NOTEBOOK_ID",
  "type": "string",
  "label": "demoNotes.session.selectedNotebook",
  "description": "Notebook used for this chat session.",
  "group": "session",
  "order": 10,
  "legacy_payload_keys": ["notebook_id"]
}
```

规则：

- scoped option 的 key 也是插件局部 key。
- `legacy_payload_keys` 只用于兼容旧请求字段。
- `visible_when` 应依赖 route、agent id 或同插件上下文，不应依赖无关全局设置。
- 项目默认项可通过 `applies_to_session_key` 初始化会话选项。

## 资源归属：`resources/resources.yaml`

插件必须声明自己拥有或影响的资源，便于 Extension Center 展示、dry-run 和审计。

```yaml
resources:
  - id: demo_notes
    type: db_collection
    scope: global
    retention_policy: keep_user_data
    cleanup_strategy: keep
    metadata:
      storage: mongodb
      purpose: Notes created by the Demo Notes plugin.
  - id: plugin-data/demo_notes
    type: plugin_data_folder
    scope: system
    retention_policy: keep_user_data
    cleanup_strategy: keep
    metadata:
      storage: local_filesystem
      purpose: Plugin runtime data directory.
  - id: plugin-data/demo_notes/config/current.json
    type: plugin_data_config
    scope: system
    retention_policy: keep_user_data
    cleanup_strategy: keep
    metadata:
      source: plugin-data-template/config/current.json
      purpose: Current plugin data-backed defaults.
```

`routes`、`tools`、`app_tabs`、`settings` 等声明式贡献点会从 manifest 自动生成资源记录；`resources.yaml` 主要补充数据库、索引、文件、plugin-data、环境变量、缓存键等非执行资源。

常见资源类型：

- `db_collection`
- `db_index`
- `file`
- `env_key_declaration`
- `message_action`
- `plugin_data_folder`
- `plugin_data_config`
- `plugin_data_storage`

清理策略建议：

- `keep`：保留用户数据。
- `archive`：可归档元数据或插件数据。
- `manual_review`：管理员人工确认。
- 当前静态内置插件阶段，不做物理删除用户数据。

## 插件数据：`plugin-data-template/` 与 `plugin-data/`

插件默认数据放在插件目录内：

```text
plugins/preinstalled/demo_notes/plugin-data-template/
```

运行时数据放在仓库根目录：

```text
plugin-data/demo_notes/
```

推荐模板结构：

```text
plugin-data-template/
  config/
    defaults.json
    current.json
  state/
    audit.jsonl
```

规则：

- `plugin-data-template/` 是随插件发布的默认数据。
- `plugin-data/{plugin_id}/` 是运行期数据，不应提交真实用户数据和密钥。
- API Key 等敏感信息应通过插件设置保存，并声明 `sensitive: true`。
- dry-run 默认 keep 或 archive 插件数据，不做自动删除。

## 开发步骤

1. 选择稳定的 `plugin_id`。
2. 新建插件文件夹。
3. 编写 `plugin.yaml`，没有设置也写 `settings: []`。
4. 如果有后端能力，编写 `backend/plugin.json`。
5. 如果有 UI 能力，编写 `frontend/plugin.json`。
6. 如果有配置项，编写 `config/schema.json` 和 `config/defaults.json`。
7. 编写 `resources/resources.yaml`，声明设置、数据、路由、工具、UI、索引等归属。
8. 新建 `plugin-data-template/` 默认数据目录。
9. 添加 manifest 校验、运行态启停、设置 API、UI 展示和资源 dry-run 测试。
10. 在 `/plugins` 检查插件状态、Settings、Resources、Uninstall Dry Run。

## 最小验证

后端插件基础验证：

```bash
pytest tests/kernel/extensions/test_plugin_runtime.py -q
pytest tests/kernel/extensions/test_plugin_packages.py -q
```

前端贡献验证：

```bash
cd frontend
pnpm test
pnpm lint
```

容器或远端验收：

- 插件出现在 `/plugins`。
- 插件 disabled 时设置仍可编辑，但不生效。
- 插件拥有的配置不出现在 System Settings。
- 插件工具、Agent、路由在 disabled 后不可执行或不可见。
- Resources 和 Uninstall Dry Run 能列出插件资源。
- `plugin-data/{plugin_id}/` 数据不会被误删。

## 当前限制

- 当前阶段是静态内置插件文件夹，不开放远程插件热安装。
- 当前不做真实物理卸载删除。
- 前端 renderer 仍需要应用构建中已有对应实现；远程插件携带任意 React 代码需要后续独立加载方案。
- 对归属不清的配置，应先保守留在核心设置，并在资源矩阵中标注待评估。
