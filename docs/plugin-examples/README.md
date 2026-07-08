# LambChat 插件制作指南

本文档面向想要自建 LambChat 插件的开发者。这里的内容不是运行时插件目录，也不会被 LambChat 自动安装；它是一套制作说明和可复制模板，用来帮助你把一个需求整理成可导入、可审核、边界清晰的插件包。

随文档提供的模板插件是 [Demo Notes](demo_notes/README.md)，路径为 `docs/plugin-examples/demo_notes/`。你可以复制它，改成自己的插件 ID、名称、权限、设置、后端能力、前端贡献点和数据目录，然后打包后从插件页面导入。

## 你最终要交付什么

一个可导入插件包应该只有一个插件根目录，根目录名必须等于 `plugin.yaml` 里的 `id`。

```text
my_plugin/
  README.md
  plugin.yaml
  backend/
    plugin.json
    routes.py
    tools.py
    lifecycle.py
  frontend/
    plugin.json
  config/
    defaults.json
    schema.json
  resources/
    resources.yaml
  plugin-data-template/
    config/
      defaults.json
      current.json
    state/
      audit.jsonl
```

最小可导入插件只需要：

```text
my_plugin/
  plugin.yaml
```

但建议从一开始就保留 `README.md`、`config/`、`resources/` 和 `plugin-data-template/`。这些文件能让插件的权限、设置、数据归属和卸载 dry-run 行为更容易审核。

## 制作流程

### 1. 先写清楚插件边界

不要先写代码。先回答这些问题：

| 问题 | 写到哪里 | 示例 |
| --- | --- | --- |
| 插件叫什么，ID 是什么 | `plugin.yaml` | `my_plugin` |
| 插件需要哪些权限 | `plugin.yaml` | `my_plugin:read`、`my_plugin:write` |
| 是否默认启用 | `plugin.yaml` | `enabled_by_default: false` |
| 用户可以配置什么 | `plugin.yaml` 或 `config/schema.json` | API Key、Base URL、默认模型 |
| 是否提供后端 API | `backend/plugin.json` | `/api/my-plugin` |
| 是否提供 Agent 工具 | `backend/plugin.json` | `my_plugin_search` |
| 是否扩展前端 UI | `frontend/plugin.json` | tab、panel、message action |
| 是否保存运行时数据 | `plugin-data-template/`、`resources/resources.yaml` | 默认配置、审计文件、索引 |

插件边界原则：

- 插件启停交给 Plugin Runtime，不要新增 `ENABLE_*` 全局开关。
- 插件配置进入插件自己的 Settings，不要回写到全局 System Settings。
- 新能力优先通过 manifest 声明，不要在核心 UI、核心路由、核心工具列表里写插件特判。
- 用户数据必须明确写入资源归属台账，卸载时默认保留或进入人工审核。

### 2. 复制模板

从文档模板复制一份到你的开发目录，例如：

```powershell
Copy-Item -Recurse .\docs\plugin-examples\demo_notes C:\plugins\my_plugin
```

模板只是起点。复制后必须把目录名、manifest、权限、模块路径、renderer 名称和文档说明全部改成你的插件。

推荐替换清单：

| 旧值 | 新值示例 | 位置 |
| --- | --- | --- |
| `demo_notes` | `my_plugin` | 文件夹名、manifest、权限、模块路径、数据目录 |
| `Demo Notes` | `My Plugin` | `README.md`、`plugin.yaml` |
| `/api/demo-notes` | `/api/my-plugin` | `backend/plugin.json`、`backend/routes.py` |
| `demo_notes_create_note` | `my_plugin_run` | `backend/plugin.json`、`backend/tools.py` |
| `demo_notes.*` | `my_plugin.*` | 前端 renderer、i18n key、qualified setting key |

可以用搜索确认没有漏改：

```powershell
rg -n "demo_notes|Demo Notes|demo-notes" C:\plugins\my_plugin
```

### 3. 编写根 manifest

`plugin.yaml` 是插件入口。它描述插件身份、权限、默认启停、设置和默认数据模板。

```yaml
id: my_plugin
name: My Plugin
version: 1.0.0
api_version: v1
install_type: user_installed
entrypoint: backend
depends_on: []
permissions:
  - my_plugin:read
  - my_plugin:write
enabled_by_default: false
settings:
  - key: API_KEY
    type: string
    label: pluginSettings.my_plugin.API_KEY.label
    description: pluginSettings.my_plugin.API_KEY.description
    default: ""
    sensitive: true
    required: false
    scope: system
    group: provider
    order: 10
data_template: plugin-data-template
```

关键规则：

- `id` 必须是安全单段名称，建议小写 snake_case。
- 插件文件夹名必须等于 `id`。
- 自建导入插件使用 `user_installed`；随仓库预装但默认可禁用的插件使用 `preinstalled`；核心系统插件使用 `system_builtin`。
- `settings` 没有配置时也要写 `settings: []`。
- 敏感配置要声明 `sensitive: true`，不要写进模板数据。
- 如果从旧全局配置迁移，可以在 setting 上声明 `legacy_system_setting_keys`。

### 4. 声明后端能力

如果插件提供 API、工具或生命周期 hook，在 `backend/plugin.json` 中声明。

```json
{
  "schema": "lambchat.plugin.backend.v1",
  "plugin_id": "my_plugin",
  "backend": {
    "routes": [
      {
        "name": "my-plugin-api",
        "prefix": "/api/my-plugin",
        "module": "plugins.installed.my_plugin.backend.routes",
        "required_permissions": ["my_plugin:read", "my_plugin:write"],
        "tags": ["My Plugin"]
      }
    ],
    "tools": [
      {
        "name": "my_plugin_run",
        "module": "plugins.installed.my_plugin.backend.tools",
        "required_permissions": ["my_plugin:write"],
        "legacy_ids": []
      }
    ],
    "lifespan_hooks": [
      {
        "name": "my_plugin:shutdown",
        "module": "plugins.installed.my_plugin.backend.lifecycle:shutdown",
        "phase": "shutdown",
        "order": 50
      }
    ]
  }
}
```

后端边界：

- 工具名使用字母、数字、下划线。
- 新工具名不要使用点号；兼容旧名字时放入 `legacy_ids`。
- 用户导入插件通常使用 `plugins.installed.{plugin_id}.backend.xxx` 模块路径。
- 导入插件包不会自动安装 Python/Node 依赖，依赖必须已在宿主环境中存在。

### 5. 声明前端贡献点

如果插件扩展 UI，在 `frontend/plugin.json` 中声明贡献点。

```json
{
  "schema": "lambchat.plugin.frontend.v1",
  "plugin_id": "my_plugin",
  "frontend": {
    "app_tabs": [
      {
        "id": "my_plugin:main-tab",
        "tab": "my-plugin",
        "path": "/my-plugin",
        "label": "myPlugin.nav.label",
        "panel": "my_plugin:main-panel",
        "insert_after": "settings",
        "order": 650,
        "permissions": ["my_plugin:read"]
      }
    ],
    "app_panels": [
      {
        "id": "my_plugin:main-panel",
        "tab": "my-plugin",
        "renderer": "my_plugin.MainPanel"
      }
    ],
    "message_actions": [
      {
        "id": "my_plugin:message-action",
        "target": "assistant_message",
        "renderer": "my_plugin.MessageAction",
        "order": 40,
        "permissions": ["my_plugin:write"]
      }
    ],
    "i18n_namespaces": ["my_plugin"],
    "required_permissions": ["my_plugin:read"]
  }
}
```

常见贡献点：

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

- 当前 renderer 必须由宿主前端已注册，或由未来插件前端加载机制提供。
- 不要为了单个插件在核心组件里写固定入口。
- 插件前端能力应通过 `frontend/plugin.json` 进入 runtime contributions。

### 6. 准备设置和默认数据

插件设置用于用户配置；`plugin-data-template/` 用于初始化非敏感默认数据。

```text
plugin-data-template/
  config/
    defaults.json
    current.json
  state/
    audit.jsonl
```

运行后数据会落到：

```text
plugin-data/my_plugin/
```

注意：

- `plugin-data-template/` 可以随插件包提交。
- `plugin-data/my_plugin/` 是运行时数据，不应该打进插件包。
- API Key、token、用户隐私数据不能写入模板。
- 敏感值使用插件 settings，并声明 `sensitive: true`。

### 7. 声明资源归属

`resources/resources.yaml` 用来说明插件拥有或影响哪些数据、文件、索引和外部资源，方便导入、审核和卸载 dry-run。

```yaml
resources:
  - id: my_plugin
    type: db_collection
    scope: global
    retention_policy: keep_user_data
    cleanup_strategy: keep
    metadata:
      storage: mongodb
      purpose: Records created by My Plugin.
  - id: plugin-data/my_plugin
    type: plugin_data_folder
    scope: system
    retention_policy: keep_user_data
    cleanup_strategy: keep
    metadata:
      storage: local_filesystem
      purpose: Plugin runtime data directory.
  - id: plugin-data/my_plugin/config/current.json
    type: plugin_data_config
    scope: system
    retention_policy: keep_user_data
    cleanup_strategy: keep
    metadata:
      source: plugin-data-template/config/current.json
      purpose: Current plugin data-backed defaults.
```

推荐策略：

- 用户数据：`retention_policy: keep_user_data`、`cleanup_strategy: keep`
- 索引或元数据：`retention_policy: archive_metadata`、`cleanup_strategy: archive`
- 凭据或不确定资源：`retention_policy: manual_review_required`、`cleanup_strategy: manual_review`

### 8. 打包插件

打包前确认当前目录结构是：

```text
C:\plugins\
  my_plugin\
    plugin.yaml
    README.md
    backend\
    frontend\
    config\
    resources\
    plugin-data-template\
```

打 zip 包：

```powershell
Compress-Archive -Path C:\plugins\my_plugin -DestinationPath C:\plugins\my_plugin.zip -Force
```

或者打 tar 包：

```bash
tar -czf my_plugin.tgz my_plugin
```

压缩包顶层必须只包含一个插件目录。不要把这些内容打进包：

```text
plugin-data/my_plugin/
node_modules/
.venv/
__pycache__/
.git/
dist cache/
secrets.json
.env
```

### 9. 在插件页面导入

1. 打开 Extension Center / Plugins。
2. 找到 Import local plugin package。
3. 输入本地文件夹或压缩包路径。
4. 点击 Dry Run。
5. 检查 `actions`、`warnings`、`sha256`、`target_path`、`data_dir`。
6. 确认没有错误后点击 Import。
7. 重启或重新扫描插件包。
8. 在插件详情页完成 review/signature 后启用。

导入成功后通常会生成：

```text
plugins/installed/my_plugin/
plugin-data/my_plugin/
```

当前导入边界：

- 支持本地文件夹、`.zip`、`.tar`、`.tar.gz`、`.tgz`。
- 单个包最大约 50 MB。
- 最多约 2000 个文件。
- 不允许 symlink。
- archive 路径不能包含 `..`、空段或逃逸目录。
- 导入不会热加载代码，不会动态安装依赖。
- 未签名插件默认保持 disabled，需要经过本地 review 或未来签名校验后再启用。

## 制作完成检查表

提交或分发插件包前逐项确认：

- `plugin.yaml` 存在，且 `id` 等于文件夹名。
- `README.md` 写清楚插件用途、权限、设置、数据和限制。
- 所有插件配置都在插件 settings 中声明。
- 没有新增 `ENABLE_*` 插件开关。
- 没有在核心 UI、核心路由、核心工具列表里写插件特判。
- `backend/plugin.json` 的 `plugin_id` 正确。
- `frontend/plugin.json` 的 `plugin_id` 正确。
- `config/schema.json` 可被 JSON 解析。
- `resources/resources.yaml` 声明了数据、文件、索引等资源归属。
- `plugin-data-template/` 存在，并且不包含秘密信息。
- 包大小小于 50 MB，文件数少于 2000。
- 不包含 symlink。
- archive 顶层只有一个插件目录。
- 导入 dry-run 无错误。

## 模板文件说明

文档模板位于：

```text
docs/plugin-examples/demo_notes/
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

推荐阅读顺序：

1. [完整插件开发规范](../plugin-development.md)
2. [Demo Notes 模板说明](demo_notes/README.md)
3. [根 manifest 模板](demo_notes/plugin.yaml)
4. [后端 manifest 模板](demo_notes/backend/plugin.json)
5. [前端 manifest 模板](demo_notes/frontend/plugin.json)
6. [资源归属台账模板](demo_notes/resources/resources.yaml)
