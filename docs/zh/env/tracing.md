# 链路追踪配置

LangSmith 链路追踪设置，用于可观测性和调试。

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `LANGSMITH_TRACING` | `false` | 否 | 启用 LangSmith 链路追踪。 |
| `LANGSMITH_API_KEY` | _(空)_ | 是 | LangSmith API 密钥。 |
| `LANGSMITH_PROJECT` | `lambchat` | 否 | LangSmith 项目名称。 |
| `LANGSMITH_API_URL` | `https://api.smith.langchain.com` | 否 | LangSmith API 端点。 |
| `LANGSMITH_SAMPLE_RATE` | `1.0` | 否 | 追踪采样率（0.0 到 1.0）。 |

## 示例

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_xxxxxxxxxxxxx
LANGSMITH_PROJECT=lambchat-prod
LANGSMITH_SAMPLE_RATE=1.0
```

::: tip
- 在生产环境中设置 `LANGSMITH_SAMPLE_RATE` 为 `0.1` 以仅追踪 10% 的请求
- 使用 `LANGSMITH_PROJECT` 按环境组织追踪（如 `lambchat-dev`、`lambchat-prod`）
- 在 [smith.langchain.com](https://smith.langchain.com) 查看你的追踪数据
:::
