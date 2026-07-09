# 会话配置

管理聊天会话、事件流和会话标题的设置。

## 会话限制

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SESSION_MAX_RUNS_PER_SESSION` | `100` | 每个会话的最大 Agent 运行次数。 |
| `SESSION_MAX_MESSAGES` | `20` | 每个会话加载的最大消息数（内部配置，不在 `.env` 中）。 |
| `SESSION_MAX_EVENTS_PER_TRACE` | `50000` | 每个 trace 保留的最大事件数，防止内存溢出。 |
| `SESSION_EVENT_CHUNK_STORAGE_ENABLED` | `false` | 将新 trace 事件写入 `trace_event_chunks`，而不是旧的 `traces.events` 数组。 |
| `SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY` | `false` | 开启分片存储后，在短期回滚窗口内同时写旧的 `traces.events`。 |
| `SESSION_EVENT_CHUNK_SIZE` | `5000` | 每个 trace event chunk 文档最多保存的事件数。这只是存储分片大小，不是读取上限。 |

## 消息历史

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_MESSAGE_HISTORY` | `true` | 启用消息历史存储。 |
| `SSE_CACHE_TTL` | `86400` | Redis 中运行中 SSE 事件的 TTL（秒），默认 24 小时；任务结束后会缩短为 60 秒。 |

## 事件合并

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_EVENT_MERGER` | `true` | 启用事件合并以减少冗余 SSE 事件。 |
| `EVENT_MERGE_INTERVAL` | `300.0` | 合并间隔（秒）。 |
| `EVENT_MERGE_MAX_EVENTS_PER_TRACE` | `50000` | 已完成 trace 可参与合并的最大事件数。 |
| `EVENT_MERGE_IMMEDIATE_DEBOUNCE_SECONDS` | `2.0` | trace 完成后聚合即时合并请求的延迟窗口。 |

## 会话标题生成

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SESSION_TITLE_MODEL` | _(空)_ | 用于生成会话标题的管理员模型配置 ID。空 = `DEFAULT_MODEL_ID` / 默认模型。旧的模型值仍兼容。 |
| `SESSION_TITLE_API_BASE` | _(空)_ | 兼容旧配置保留。标题生成现在使用 `SESSION_TITLE_MODEL` 或默认模型里的 provider/API 地址。 |
| `SESSION_TITLE_API_KEY` | _(空)_ | 兼容旧配置保留。标题生成现在使用 `SESSION_TITLE_MODEL` 或默认模型里的 API 密钥。**敏感信息。** |
| `SESSION_TITLE_PROMPT` | _(长中文提示)_ | 标题生成的提示模板。支持 `{lang}` 和 `{message}` 占位符。 |

::: tip
通过 `SESSION_TITLE_MODEL` 选择模型管理里已有的模型配置。留空则使用 `DEFAULT_MODEL_ID` / 默认模型。
:::

## 示例

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
