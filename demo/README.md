# LambChat 插件开发 Demo

这个目录是一份面向插件开发者的入门包。目标不是只展示一个 manifest，而是说明如何从需求拆分、目录组织、边界配置、默认数据、资源归属到最终打包，生成一个可以在 LambChat 插件页面导入的本地插件包。

当前示例插件为 `demo_notes`，位于 [demo_notes](demo_notes)。它不会从 `demo/` 自动安装，适合复制、改名、扩展后打包导入。

## 当前导入能力边界

LambChat 插件页面当前支持导入本地插件包，入口在 Extension Center / Plugins 的 Import local plugin package 区域。

支持的导入源：

- 本地插件文件夹路径，例如 `C:\plugins\demo_notes`
- `.zip`
- `.tar`
- `.tar.gz`
- `.tgz`

导入行为：

- 先点 Dry Run 校验包结构、manifest、资源、hash 和将要执行的动作。
- 再点 Import 将包复制到 `plugins/installed/{plugin_id}`。
- 导入不会热加载代码，不会动态安装依赖，需要重启或重新扫描后才会进入运行时。
- 用户安装的未签名插件默认保持 disabled，必须经过本地 review 或未来签名校验后再启用。
- 当前阶段不支持远程插件热安装，不支持真实物理卸载删除用户数据。

安全限制：

- 单个包最大约 50 MB。
- 最多约 2000 个文件。
- 不允许 symlink。
- archive 里必须只有一个包含 `plugin.yaml` 的插件根目录。
- archive 路径不能包含 `..`、空段或逃逸目录的路径。
- `plugin.yaml` 的 `id` 必须和插件文件夹名一致。

## 从需求到插件包

开发一个插件时，先写清楚这几类需求：

| 需求类型 | 应放位置 | 示例 |
| --- | --- | --- |
| 插件身份、权限、启停默认值 | `plugin.yaml` | `id`、`permissions`、`enabled_by_default` |
| 插件设置 | `plugin.yaml` 或 `config/schema.json` | API Key、Base URL、默认模型、限额 |
| 后端 API | `backend/plugin.json` | `/api/demo-notes` |
| Agent 工具 | `backend/plugin.json` | `demo_notes_create_note` |
| Agent | `backend/plugin.json` | 插件自带 Agent |
| 前端页面 | `frontend/plugin.json` | `/demo-notes` tab |
| 消息按钮 | `frontend/plugin.json` | assistant message action |
| 聊天输入扩展 | `frontend/plugin.json` | team picker、connector picker |
| 项目/会话/渠道/定时任务选项 | `frontend/plugin.json` | `session_options`、`project_options` |
| 默认数据 | `plugin-data-template/` | 默认配置、空审计文件 |
| 资源归属和卸载 dry-run | `resources/resources.yaml` | collection、index、file、setting、UI action |

## 标准插件目录

```text
{plugin_id}/
  README.md
  plugin.yaml
  backend/
    plugin.json
    routes.py
    tools.py
    lifecycle.py
  frontend/
    plugin.json
    dist/
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
```

最小必需文件：

```text
{plugin_id}/
  plugin.yaml
```

推荐最小可维护文件：

```text
{plugin_id}/
  README.md
  plugin.yaml
  config/schema.json
  resources/resources.yaml
  plugin-data-template/config/defaults.json
  plugin-data-template/config/current.json
  plugin-data-template/state/audit.jsonl
```

## 根 manifest 示例

`plugin.yaml` 是插件包入口，字段要尽量完整。

```yaml
id: demo_notes
name: Demo Notes
version: 1.0.0
api_version: v1
install_type: preinstalled
entrypoint: backend
depends_on: []
permissions:
  - demo_notes:read
  - demo_notes:write
enabled_by_default: false
settings:
  - key: NOTEBOOK_NAME
    type: string
    label: pluginSettings.demo_notes.NOTEBOOK_NAME.label
    description: pluginSettings.demo_notes.NOTEBOOK_NAME.description
    default: Inbox
    scope: system
    group: general
    order: 10
  - key: MAX_NOTE_LENGTH
    type: number
    label: pluginSettings.demo_notes.MAX_NOTE_LENGTH.label
    description: pluginSettings.demo_notes.MAX_NOTE_LENGTH.description
    default: 2000
    scope: system
    group: limits
    order: 20
data_template: plugin-data-template
```

边界规则：

- `id` 只能是安全单段路径名，不能包含 `/`、`\`、`.`、`..`。
- 文件夹名必须等于 `id`。
- `settings` 没有配置时也要写 `settings: []`。
- 插件启停不要用 `ENABLE_*`，必须交给 Plugin Runtime。
- 插件配置不要放回 System Settings。

## 插件设置参数示例

插件设置会自动进入插件页面 Settings 区。

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
  - key: MODE
    type: select
    label: pluginSettings.demo_notes.MODE.label
    description: pluginSettings.demo_notes.MODE.description
    default: standard
    scope: system
    group: behavior
    order: 20
    options:
      - standard
      - strict
      - experimental
  - key: ADVANCED_OPTIONS
    type: json
    label: pluginSettings.demo_notes.ADVANCED_OPTIONS.label
    description: pluginSettings.demo_notes.ADVANCED_OPTIONS.description
    default: {}
    scope: system
    group: advanced
    order: 30
```

设置边界：

- `key` 是插件局部 key，系统会组合成 `demo_notes.API_KEY`。
- `sensitive: true` 的值会在 API 中 mask，提交 `********` 表示保持原值。
- `env_fallback` 只作为初始导入/缺省值，不是 UI 的主数据源。
- `legacy_system_setting_keys` 用于从旧 System Settings 迁移，并隐藏旧全局 key。
- `scope` 当前推荐先用 `system`；`user`、`role` 可预留，但不要扩大权限面。

## 后端能力示例

`backend/plugin.json` 声明后端能力。

```json
{
  "schema": "lambchat.plugin.backend.v1",
  "plugin_id": "demo_notes",
  "backend": {
    "routes": [
      {
        "name": "demo_notes-api",
        "prefix": "/api/demo-notes",
        "module": "plugins.installed.demo_notes.backend.routes",
        "required_permissions": ["demo_notes:read", "demo_notes:write"],
        "tags": ["Demo Notes"]
      }
    ],
    "tools": [
      {
        "name": "demo_notes_create_note",
        "module": "plugins.installed.demo_notes.backend.tools",
        "required_permissions": ["demo_notes:write"],
        "legacy_ids": ["demo_notes.create_note"]
      }
    ],
    "lifespan_hooks": [
      {
        "name": "demo_notes:shutdown",
        "module": "plugins.installed.demo_notes.backend.lifecycle:close_demo_notes",
        "phase": "shutdown",
        "order": 50
      }
    ]
  }
}
```

边界规则：

- 工具名使用模型安全格式：字母、数字、下划线。
- 新工具不要用点号；旧点号名称放进 `legacy_ids`。
- `module` 必须是运行环境可 import 的模块。用户导入包通常写成 `plugins.installed.{plugin_id}.backend.xxx`；系统内置插件如果代码放在 `src/` 内，则可以写成 `src.plugins.xxx`、`src.api.xxx` 或 `src.infra.xxx`。
- 导入插件包不会自动安装 Python/Node 依赖；依赖必须已在宿主环境中存在，或等未来插件依赖安装机制。

## 前端能力示例

`frontend/plugin.json` 声明 UI 扩展点。

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

常见可声明项：

- `app_tabs`
- `app_panels`
- `sidebar_items`
- `user_menu_items`
- `message_actions`
- `tool_renderers`
- `chat_input_options`
- `chat_input_panels`
- `mention_providers`
- `welcome_surfaces`
- `assistant_identity_resolvers`
- `agent_categories`
- `project_options`
- `session_options`
- `channel_options`
- `scheduled_task_options`

前端边界：

- 当前 renderer 必须由宿主前端已注册或未来插件前端加载机制提供。
- `frontend/dist/` 可以作为包结构的一部分被扫描，但当前阶段不是远程热加载任意 React 代码。
- 不要在核心 UI 中为插件写硬编码入口；优先声明贡献点。

## 作用域选项示例

如果插件需要在项目、会话、渠道或定时任务里保存选择项，使用 scoped options。

```json
{
  "key": "SELECTED_NOTEBOOK_ID",
  "type": "string",
  "label": "demoNotes.session.selectedNotebook",
  "description": "Notebook used by the current chat session.",
  "group": "session",
  "order": 10,
  "renderer": "demo_notes.NotebookSelectOption",
  "legacy_payload_keys": ["notebook_id"]
}
```

项目默认值应用到会话：

```json
{
  "key": "DEFAULT_NOTEBOOK_ID",
  "type": "string",
  "label": "demoNotes.project.defaultNotebook",
  "group": "project",
  "order": 10,
  "renderer": "demo_notes.NotebookSelectOption",
  "applies_to_session_key": "SELECTED_NOTEBOOK_ID"
}
```

## 资源归属和 dry-run 示例

`resources/resources.yaml` 声明插件拥有或影响的资源。

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
  - id: demo_notes.user_lookup
    type: db_index
    scope: global
    retention_policy: archive_metadata
    cleanup_strategy: archive
    metadata:
      collection: demo_notes
      fields: user_id,created_at:-1
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

注意：`app_tabs`、`tools`、`routes`、`settings` 等声明式贡献点会由 Runtime 从 `plugin.yaml`、`backend/plugin.json`、`frontend/plugin.json` 自动登记资源台账；`resources.yaml` 主要补充数据库、文件、plugin-data、环境变量、索引等非执行资源。

推荐策略：

- 用户数据：`retention_policy: keep_user_data`、`cleanup_strategy: keep`
- 索引/元数据：`archive_metadata`、`archive`
- 凭据或不确定资源：`manual_review_required`、`manual_review`

## plugin-data 约定

插件包内提供默认数据：

```text
demo_notes/plugin-data-template/
  config/
    defaults.json
    current.json
  state/
    audit.jsonl
```

导入或运行后，运行时数据目录是：

```text
plugin-data/demo_notes/
```

边界：

- `plugin-data-template/` 可以随插件包提交。
- `plugin-data/demo_notes/` 是运行时数据，不应打进插件包。
- 不要把 API Key、token、用户隐私数据写入模板。
- 敏感值使用插件 settings，并声明 `sensitive: true`。

## 打包成可导入插件包

从 `demo/demo_notes` 复制出真实插件后，确保根目录就是插件文件夹，例如：

```text
demo_notes/
  plugin.yaml
  backend/
  frontend/
  config/
  resources/
  plugin-data-template/
```

打 zip 包时，zip 顶层必须只包含一个插件目录：

```powershell
Compress-Archive -Path .\demo_notes -DestinationPath .\demo_notes.zip -Force
```

或者使用 tar：

```bash
tar -czf demo_notes.tgz demo_notes
```

不要把这些内容打进包里：

```text
plugin-data/demo_notes/
node_modules/
.venv/
__pycache__/
.git/
dist cache/
secrets.json
.env
```

## 在插件页面导入

1. 打开 Extension Center / Plugins。
2. 找到 Import local plugin package。
3. 输入本地路径，例如：

```text
C:\Users\admin\Desktop\demo_notes.zip
```

或文件夹：

```text
C:\Users\admin\Desktop\demo_notes
```

4. 点击 Dry Run。
5. 确认 actions、warnings、sha256、target_path、data_dir。
6. 点击 Import。
7. 重启或重新扫描插件包。
8. 在插件详情页完成 review/signature 后启用。

导入成功后目标位置通常是：

```text
plugins/installed/demo_notes/
plugin-data/demo_notes/
```

## 开发者交付清单

交付插件包前逐项检查：

- `plugin.yaml` 存在，且 `id` 等于文件夹名。
- `README.md` 写清楚插件用途、权限、设置、数据和限制。
- 所有插件配置都在插件 settings 中声明。
- 没有继续使用 `ENABLE_*` 作为插件开关。
- `backend/plugin.json` 的 `plugin_id` 正确。
- `frontend/plugin.json` 的 `plugin_id` 正确。
- `config/schema.json` 可被 JSON 解析。
- `resources/resources.yaml` 声明了数据、设置、UI、工具、路由、索引等资源。
- `plugin-data-template/` 存在，并且不包含秘密信息。
- 包大小小于 50 MB，文件数少于 2000。
- 不包含 symlink。
- archive 顶层只有一个插件目录。
- 导入 dry-run 无错误。

## 本 demo 包含的文件

```text
demo/demo_notes/
  README.md
  plugin.yaml
  backend/
    __init__.py
    lifecycle.py
    plugin.json
    routes.py
    tools.py
  frontend/
    plugin.json
  config/
    defaults.json
    schema.json
  resources/
    resources.yaml
  plugin-data-template/
    config/
      current.json
      defaults.json
    state/
      audit.jsonl
```

## 推荐阅读

- [完整插件开发文档](../docs/plugin-development.md)
- [Demo Notes 插件说明](demo_notes/README.md)
- [根 manifest](demo_notes/plugin.yaml)
- [后端 manifest](demo_notes/backend/plugin.json)
- [前端 manifest](demo_notes/frontend/plugin.json)
- [资源归属台账](demo_notes/resources/resources.yaml)
