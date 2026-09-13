# Frontend Configuration

Frontend display and behavior settings.

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_AGENT` | `fast` | Default agent ID when creating new sessions. |
| `WELCOME_SUGGESTIONS` | _(4-item list)_ | Welcome page suggestion items. JSON array of `{icon, text}` objects. |
| `FRONTEND_DEV_URL` | _(empty)_ | Frontend dev server URL for CORS. Only needed in development. |
| `VITE_API_BASE` | _(empty)_ | API base URL for frontend fetch calls. Leave empty for same-origin. |

## WELCOME_SUGGESTIONS Format

```json
[
  {"icon": "🐍", "text": "Create a Python hello world script"},
  {"icon": "📁", "text": "List files in the workspace directory"},
  {"icon": "📄", "text": "Read the README.md file"},
  {"icon": "🔧", "text": "Help me write a shell script"}
]
```

The suggestions support i18n with language keys:

```json
{
  "en": [{"icon": "🐍", "text": "Create a Python script"}],
  "zh": [{"icon": "🐍", "text": "创建一个 Python 脚本"}],
  "ja": [{"icon": "🐍", "text": "Pythonスクリプトを作成"}]
}
```

## Example

```bash
DEFAULT_AGENT=fast
WELCOME_SUGGESTIONS=[{"icon":"🐍","text":"Create a Python hello world script"},{"icon":"📁","text":"List files in the workspace directory"}]
FRONTEND_DEV_URL=http://localhost:3001
```
