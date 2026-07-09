# Session Configuration

Settings for managing chat sessions, event streaming, and session titles.

## Session Limits

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_MAX_RUNS_PER_SESSION` | `100` | Maximum agent runs per session. |
| `SESSION_MAX_MESSAGES` | `20` | Maximum messages loaded per session (internal, not in `.env`). |
| `SESSION_MAX_EVENTS_PER_TRACE` | `50000` | Maximum events per trace to prevent memory overflow. |
| `SESSION_EVENT_CHUNK_STORAGE_ENABLED` | `false` | Store new trace events in `trace_event_chunks` instead of the legacy `traces.events` array. |
| `SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY` | `false` | When chunk storage is enabled, also write events to legacy `traces.events` during a short rollback window. |
| `SESSION_EVENT_CHUNK_SIZE` | `5000` | Maximum events per trace event chunk document. This is a storage chunk size, not a read limit. |

## Message History

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_MESSAGE_HISTORY` | `true` | Enable message history storage. |
| `SSE_CACHE_TTL` | `86400` | Redis TTL for live SSE events in seconds (24 hours); terminal streams are shortened to 60 seconds. |

## Event Merger

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_EVENT_MERGER` | `true` | Enable event merging to reduce redundant SSE events. |
| `EVENT_MERGE_INTERVAL` | `300.0` | Merge interval in seconds. |
| `EVENT_MERGE_MAX_EVENTS_PER_TRACE` | `50000` | Maximum events per completed trace eligible for merging. |
| `EVENT_MERGE_IMMEDIATE_DEBOUNCE_SECONDS` | `2.0` | Delay used to coalesce immediate merge requests after traces complete. |

## Session Title Generation

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_TITLE_MODEL` | _(empty)_ | Admin model configuration ID used for generating session titles. Empty = `DEFAULT_MODEL_ID` / default model. Legacy model values are still supported. |
| `SESSION_TITLE_API_BASE` | _(empty)_ | Legacy compatibility setting. Title generation now uses the provider/API base from `SESSION_TITLE_MODEL` or the default model. |
| `SESSION_TITLE_API_KEY` | _(empty)_ | Legacy compatibility setting. Title generation now uses the API key from `SESSION_TITLE_MODEL` or the default model. **Sensitive.** |
| `SESSION_TITLE_PROMPT` | _(long Chinese prompt)_ | Prompt template for title generation. Supports `{lang}` and `{message}` placeholders. |

::: tip
Use `SESSION_TITLE_MODEL` to select an existing model configuration from model management. Leave it empty to use `DEFAULT_MODEL_ID` / the default model.
:::

## Example

```bash
# .env
SESSION_MAX_RUNS_PER_SESSION=100
ENABLE_MESSAGE_HISTORY=true
SSE_CACHE_TTL=86400
SESSION_EVENT_CHUNK_STORAGE_ENABLED=false
SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY=false
SESSION_EVENT_CHUNK_SIZE=5000
ENABLE_EVENT_MERGER=true
EVENT_MERGE_INTERVAL=300.0
EVENT_MERGE_MAX_EVENTS_PER_TRACE=50000
EVENT_MERGE_IMMEDIATE_DEBOUNCE_SECONDS=2.0
SESSION_TITLE_MODEL=model-config-id
```
