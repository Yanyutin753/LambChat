# MCP 与工具配置

Model Context Protocol (MCP) 和工具系统设置。

## MCP 设置

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `ENABLE_MCP` | `true` | 否 | 启用 MCP 工具系统。 |
| `MCP_ENCRYPTION_SALT` | _(自动生成)_ | 是 | 用于加密 MCP 密钥的盐值。未设置时自动生成。**建议设置以确保重启后一致性。** |

## 延迟工具加载

对于工具较多的 MCP 服务器，延迟加载通过按需加载工具来减少提示大小。

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_DEFERRED_TOOL_LOADING` | `true` | 启用延迟/懒加载工具。 |
| `DEFERRED_TOOL_THRESHOLD` | `20` | 触发延迟加载的工具数量阈值。 |
| `DEFERRED_TOOL_SEARCH_LIMIT` | `25` | 搜索返回的最大工具数。 |

## 技能

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_SKILLS` | `true` | 启用技能系统。 |
| `SKILL_PROMPT_DESCRIPTION_THRESHOLD` | `20` | Skill 数量不超过该值时显示描述；超过时保留全部名称并使用 `search_skills`。 |

## 代码解释器

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `ENABLE_CODE_INTERPRETER` | `false` | 启用实验性的 QuickJS 代码解释器供 Agent 运行使用。 |
| `CODE_INTERPRETER_PTC_TOOLS` | `web_search,web_fetch` | PTC 白名单：允许在解释器内一次执行中批量并发调用的只读工具名，逗号分隔，留空禁用。白名单工具须无人工审批门控与副作用。 |
| `CODE_INTERPRETER_SNAPSHOT_KEY` | _(空，敏感)_ | REPL 快照 HMAC 签名密钥；留空时从显式配置的 `JWT_SECRET_KEY` 派生（开发环境随机密钥下不签名）。 |

## 音频转写

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `ENABLE_AUDIO_TRANSCRIPTION` | `false` | 否 | 启用音频转写工具。 |
| `AUDIO_TRANSCRIPTION_API_KEY` | _(空)_ | 是 | 转写 API 密钥。 |
| `AUDIO_TRANSCRIPTION_BASE_URL` | _(空)_ | 否 | 转写 API 基础 URL。 |
| `AUDIO_TRANSCRIPTION_MODEL` | `gpt-4o-mini-transcribe` | 否 | 转写模型名称。 |

## 图像生成

| 变量名 | 默认值 | 敏感 | 说明 |
|--------|--------|------|------|
| `ENABLE_IMAGE_GENERATION` | `false` | 否 | 启用图像生成工具。 |
| `IMAGE_GENERATION_API_KEY` | _(空)_ | 是 | 图像生成 API 密钥。 |
| `IMAGE_GENERATION_BASE_URL` | `https://api.openai.com/v1` | 否 | OpenAI 兼容图像 API 基础 URL。 |
| `IMAGE_GENERATION_MODEL` | `gpt-image-2` | 否 | 图像模型名称。 |
| `IMAGE_GENERATION_TIMEOUT` | `120` | 否 | 请求超时时间（秒）。 |

## 示例

```bash
# MCP
ENABLE_MCP=true
MCP_ENCRYPTION_SALT=your-random-salt-here

# 技能
ENABLE_SKILLS=true

# 代码解释器（可选）
ENABLE_CODE_INTERPRETER=false
# PTC 只读工具白名单（可选；启用解释器后生效）
CODE_INTERPRETER_PTC_TOOLS=web_search,web_fetch

# 音频转写（可选）
ENABLE_AUDIO_TRANSCRIPTION=true
AUDIO_TRANSCRIPTION_API_KEY=sk-your-key
AUDIO_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe

# 图像生成（可选）
ENABLE_IMAGE_GENERATION=true
IMAGE_GENERATION_API_KEY=sk-your-key
IMAGE_GENERATION_MODEL=gpt-image-2
```

::: tip
在生产环境中务必设置 `MCP_ENCRYPTION_SALT` 为一个固定值。如果它发生变化，之前加密的 MCP 凭据将无法读取。
:::
