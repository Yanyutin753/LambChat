# MCP & Tools Configuration

Model Context Protocol (MCP) and tool system settings.

## MCP Settings

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `ENABLE_MCP` | `true` | No | Enable MCP tool system. |
| `MCP_ENCRYPTION_SALT` | _(auto-generated)_ | Yes | Salt for encrypting MCP secrets. Auto-generated if not set. **Recommended to set for consistency across restarts.** |

## Deferred Tool Loading

For MCP servers with many tools, deferred loading reduces prompt size by loading tools on-demand.

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_DEFERRED_TOOL_LOADING` | `true` | Enable deferred/lazy tool loading. |
| `DEFERRED_TOOL_THRESHOLD` | `20` | Tool count threshold to trigger deferred loading. |
| `DEFERRED_TOOL_SEARCH_LIMIT` | `25` | Maximum tools returned in a search. |

## Skills

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_SKILLS` | `true` | Enable the skills system. |
| `SKILL_PROMPT_DESCRIPTION_THRESHOLD` | `20` | Include Skill descriptions at or below this count; larger inventories list every name and use `search_skills`. |

## Code Interpreter

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_CODE_INTERPRETER` | `false` | Enable the experimental QuickJS code interpreter for agent runs. |
| `CODE_INTERPRETER_PTC_TOOLS` | `web_search,web_fetch` | PTC allowlist: read-only tool names the interpreter may batch-call concurrently in one execution, comma-separated; empty disables. Allowlisted tools must have no human-approval gating or side effects. |
| `CODE_INTERPRETER_SNAPSHOT_KEY` | _(empty, sensitive)_ | HMAC signing key for REPL snapshots; when empty, derived from an explicitly configured `JWT_SECRET_KEY` (unsigned under the dev-only random secret). |

## Audio Transcription

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `ENABLE_AUDIO_TRANSCRIPTION` | `false` | No | Enable audio transcription tool. |
| `AUDIO_TRANSCRIPTION_API_KEY` | _(empty)_ | Yes | Transcription API key. |
| `AUDIO_TRANSCRIPTION_BASE_URL` | _(empty)_ | No | Transcription API base URL. |
| `AUDIO_TRANSCRIPTION_MODEL` | `gpt-4o-mini-transcribe` | No | Transcription model name. |

## Image Generation

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `ENABLE_IMAGE_GENERATION` | `false` | No | Enable the image generation tool. |
| `IMAGE_GENERATION_API_KEY` | _(empty)_ | Yes | Image generation API key. |
| `IMAGE_GENERATION_BASE_URL` | `https://api.openai.com/v1` | No | OpenAI-compatible image API base URL. |
| `IMAGE_GENERATION_MODEL` | `gpt-image-2` | No | Image model name. |
| `IMAGE_GENERATION_TIMEOUT` | `120` | No | Request timeout in seconds. |

## Example

```bash
# MCP
ENABLE_MCP=true
MCP_ENCRYPTION_SALT=your-random-salt-here

# Skills
ENABLE_SKILLS=true

# Code Interpreter (optional)
ENABLE_CODE_INTERPRETER=false
# PTC read-only tool allowlist (optional; effective once the interpreter is on)
CODE_INTERPRETER_PTC_TOOLS=web_search,web_fetch

# Audio Transcription (optional)
ENABLE_AUDIO_TRANSCRIPTION=true
AUDIO_TRANSCRIPTION_API_KEY=sk-your-key
AUDIO_TRANSCRIPTION_MODEL=gpt-4o-mini-transcribe

# Image Generation (optional)
ENABLE_IMAGE_GENERATION=true
IMAGE_GENERATION_API_KEY=sk-your-key
IMAGE_GENERATION_MODEL=gpt-image-2
```

::: tip
Set `MCP_ENCRYPTION_SALT` to a stable value in production. If it changes, previously encrypted MCP credentials will become unreadable.
:::
