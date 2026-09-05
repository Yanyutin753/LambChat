# LLM Configuration

Settings for controlling how LambChat interacts with language models.

## Model Provider Keys

These are consumed by the underlying LLM SDK libraries directly (not by the Settings class):

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | Default LLM API key (consumed by LiteLLM) |
| `LLM_API_BASE` | Default LLM API base URL (consumed by LiteLLM) |
| `LLM_MODEL` | Default LLM model name, e.g. `anthropic/claude-sonnet-4-6` |
| `ANTHROPIC_API_KEY` | Anthropic API key (consumed by `langchain-anthropic`) |
| `ANTHROPIC_BASE_URL` | Anthropic-compatible API base URL |

::: tip
LambChat supports multi-model management through the UI. The env vars above set the **default** provider. Users can add additional providers and models at runtime through the settings panel.
:::

## Retry & Cache Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEFAULT_MODEL_ID` | _(empty)_ | Admin model configuration ID used as the default for new sessions and background jobs. Empty = first enabled model. |
| `LLM_MAX_RETRIES` | `3` | Retries after the initial call for timeout, network, rate-limit, and 5xx failures. `3` means up to 4 attempts. |
| `LLM_RETRY_DELAY` | `1.0` | Initial retry delay in seconds (exponential backoff). |
| `LLM_REQUEST_TIMEOUT` | `0` | Total seconds allowed for a complete non-streaming response. `0` or a negative value disables LambChat's non-streaming total timeout, so non-streaming waits indefinitely by default. |
| `LLM_FIRST_EVENT_TIMEOUT` | `30` | Seconds allowed for the first provider event of a streaming response. `0` or a negative value disables this deadline. No total duration limit applies after the first event. |
| `LLM_STREAM_IDLE_TIMEOUT` | `120` | Maximum idle seconds between consecutive streaming chunks, so an upstream relay stall fails the call instead of hanging the run forever. `0` or a negative value disables it. |
| `LLM_MODEL_CACHE_SIZE` | `50` | Model instance cache size. Prevents memory leaks from repeated instantiation. |
| `LLM_REQUEST_HEADERS` | _(empty)_ | JSON object of request headers merged over the built-in anti-ban defaults (Claude Code style `User-Agent`/`x-app` for Anthropic protocol, opencode style `User-Agent` for OpenAI-compatible). Example: `{"User-Agent": "my-agent/1.0"}`. Per-model header overrides take precedence; Google protocol is not supported. |
| `LLM_MAX_INPUT_TOKENS` | _(none)_ | Optional: context window size for DeepAgent auto-summarization. |
| `LLM_TEMPERATURE` | _(none)_ | Optional: default temperature for LLM calls. |
| `LLM_MAX_TOKENS` | _(none)_ | Optional: max output tokens for LLM calls. |

## DeepAgent Context Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPAGENT_DEFAULT_MAX_INPUT_TOKENS` | `64000` | Default max input tokens for DeepAgent. |

## Example

```bash
# .env
LLM_API_KEY=sk-your-api-key
LLM_API_BASE=https://api.openai.com/v1
LLM_MODEL=gpt-4o
LLM_MAX_RETRIES=3
LLM_RETRY_DELAY=1.0
LLM_REQUEST_TIMEOUT=0
LLM_FIRST_EVENT_TIMEOUT=30
LLM_STREAM_IDLE_TIMEOUT=120
LLM_MODEL_CACHE_SIZE=50
```
