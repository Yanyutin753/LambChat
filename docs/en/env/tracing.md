# Tracing Configuration

LangSmith tracing settings for observability and debugging.

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `LANGSMITH_TRACING` | `false` | No | Enable LangSmith tracing. |
| `LANGSMITH_API_KEY` | _(empty)_ | Yes | LangSmith API key. |
| `LANGSMITH_PROJECT` | `lambchat` | No | LangSmith project name. |
| `LANGSMITH_API_URL` | `https://api.smith.langchain.com` | No | LangSmith API endpoint. |
| `LANGSMITH_SAMPLE_RATE` | `1.0` | No | Tracing sample rate (0.0 to 1.0). |

## Example

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_xxxxxxxxxxxxx
LANGSMITH_PROJECT=lambchat-prod
LANGSMITH_SAMPLE_RATE=1.0
```

::: tip
- Set `LANGSMITH_SAMPLE_RATE` to `0.1` in production to trace only 10% of requests
- Use `LANGSMITH_PROJECT` to organize traces by environment (e.g., `lambchat-dev`, `lambchat-prod`)
- Access your traces at [smith.langchain.com](https://smith.langchain.com)
:::
