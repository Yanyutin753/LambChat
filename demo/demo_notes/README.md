# Demo Notes 插件

Demo Notes 是一个 LambChat 插件开发示例，用来展示文件夹式插件可以声明哪些能力。它不会从 `demo/` 自动安装。

## 能力示例

- 插件设置 schema。
- 后端 API 前缀：`/api/demo-notes`。
- Agent 工具：`demo_notes_create_note`。
- 前端页面 tab。
- assistant message action。
- 工具调用渲染器声明。
- 插件资源归属和 dry-run 策略。
- `plugin-data-template/` 默认数据。

## 设置项

| Key | Type | Scope | 说明 |
| --- | --- | --- | --- |
| `NOTEBOOK_NAME` | `string` | `system` | 默认笔记本名称。 |
| `ALLOW_MESSAGE_ACTION` | `boolean` | `system` | 是否展示消息保存按钮。 |
| `MAX_NOTE_LENGTH` | `number` | `system` | 笔记最大长度。 |

对应 qualified keys：

```text
demo_notes.NOTEBOOK_NAME
demo_notes.ALLOW_MESSAGE_ACTION
demo_notes.MAX_NOTE_LENGTH
```

## 数据目录

默认数据：

```text
plugin-data-template/config/defaults.json
plugin-data-template/config/current.json
plugin-data-template/state/audit.jsonl
```

运行时数据：

```text
plugin-data/demo_notes/
```

## 安全约束

示例插件把用户数据声明为 `keep_user_data`。dry-run 可以展示它拥有的资源，但不应自动删除用户笔记或插件运行数据。

