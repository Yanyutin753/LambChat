# 前端配置

前端显示和行为设置。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DEFAULT_AGENT` | `fast` | 创建新会话时的默认 Agent ID。 |
| `WELCOME_SUGGESTIONS` | _(4 项列表)_ | 欢迎页建议项。`{icon, text}` 对象的 JSON 数组。 |
| `FRONTEND_DEV_URL` | _(空)_ | 前端开发服务器 URL，用于 CORS。仅在开发时需要。 |
| `VITE_API_BASE` | _(空)_ | 前端 fetch 调用的 API 基础 URL。留空表示同源。 |

## WELCOME_SUGGESTIONS 格式

```json
[
  {"icon": "🐍", "text": "创建一个 Python Hello World 脚本"},
  {"icon": "📁", "text": "列出工作区目录中的文件"},
  {"icon": "📄", "text": "读取 README.md 文件"},
  {"icon": "🔧", "text": "帮我写一个 Shell 脚本"}
]
```

建议支持国际化语言键：

```json
{
  "en": [{"icon": "🐍", "text": "Create a Python script"}],
  "zh": [{"icon": "🐍", "text": "创建一个 Python 脚本"}],
  "ja": [{"icon": "🐍", "text": "Pythonスクリプトを作成"}]
}
```

## 示例

```bash
DEFAULT_AGENT=fast
WELCOME_SUGGESTIONS=[{"icon":"🐍","text":"创建一个 Python Hello World 脚本"},{"icon":"📁","text":"列出工作区目录中的文件"}]
FRONTEND_DEV_URL=http://localhost:3001
```
