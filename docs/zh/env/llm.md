# LLM 配置

控制 LambChat 与语言模型交互方式的设置。

## 模型提供商密钥

这些变量由底层 LLM SDK 库直接使用（不经过 Settings 类）：

| 变量名 | 说明 |
|--------|------|
| `LLM_API_KEY` | 默认 LLM API 密钥（由 LiteLLM 使用） |
| `LLM_API_BASE` | 默认 LLM API 基础 URL（由 LiteLLM 使用） |
| `LLM_MODEL` | 默认 LLM 模型名称，如 `anthropic/claude-sonnet-4-6` |
| `ANTHROPIC_API_KEY` | Anthropic API 密钥（由 `langchain-anthropic` 使用） |
| `ANTHROPIC_BASE_URL` | Anthropic 兼容的 API 基础 URL |

::: tip
LambChat 支持通过 UI 进行多模型管理。以上环境变量设置的是**默认**提供商。用户可以在运行时通过设置面板添加额外的提供商和模型。
:::

## 重试与缓存设置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DEFAULT_MODEL_ID` | _(空)_ | 管理员设置的新会话和后台任务默认模型配置 ID。空 = 第一个启用模型。 |
| `LLM_MAX_RETRIES` | `3` | 超时、网络、限流和 5xx 失败后追加的重试次数。`3` 表示最多调用 4 次。 |
| `LLM_RETRY_DELAY` | `1.0` | 首次重试等待时间（秒，后续指数退避）。 |
| `LLM_REQUEST_TIMEOUT` | `0` | 完整非流式响应的总时限（秒）。`0` 或负数禁用 LambChat 的非流式总超时，因此非流式默认无限等待。 |
| `LLM_FIRST_EVENT_TIMEOUT` | `30` | 流式响应首个 provider 事件的最长等待秒数。`0` 或负数禁用该 deadline。首事件到达后，LambChat 无流式总时限或 chunk 空闲超时。 |
| `LLM_MODEL_CACHE_SIZE` | `50` | 模型实例缓存大小。防止重复实例化导致的内存泄漏。 |
| `LLM_MAX_INPUT_TOKENS` | _(无)_ | 可选：DeepAgent 自动摘要的上下文窗口大小。 |
| `LLM_TEMPERATURE` | _(无)_ | 可选：LLM 调用的默认温度。 |
| `LLM_MAX_TOKENS` | _(无)_ | 可选：LLM 调用的最大输出 token 数。 |

## DeepAgent 上下文设置

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `DEEPAGENT_DEFAULT_MAX_INPUT_TOKENS` | `64000` | DeepAgent 默认最大输入 token 数。 |

## 示例

```bash
# .env
LLM_API_KEY=sk-your-api-key
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LLM_MAX_RETRIES=3
LLM_RETRY_DELAY=1.0
LLM_REQUEST_TIMEOUT=0
LLM_FIRST_EVENT_TIMEOUT=30
LLM_MODEL_CACHE_SIZE=50
```
