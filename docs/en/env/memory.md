# Memory Configuration

Cross-session memory system settings. LambChat uses a native MongoDB-backed memory system with embedding semantic search, query-time relevance injection, self-evolving lesson distillation, and optional Qdrant vector backend.

Each user can toggle memory on/off in **Profile → Preferences → Cross-session memory** (default: enabled). When disabled: no auto-capture, no index/query-context injection, memory tools unavailable; panel manual management still works, data preserved.

## Master Switch

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_MEMORY` | `false` | Enable cross-session memory system (server-level master switch). |
| `ENABLE_MEMORY_VFS` | `false` | Enable `/memories/working/` agent-managed task-note layer for multi-turn workflows. See VFS Working Memory section. |

## Embedding Settings

For semantic search over memories. Leave empty for text-only (no embedding) mode.

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `NATIVE_MEMORY_EMBEDDING_API_BASE` | _(empty)_ | No | OpenAI-compatible embedding API base URL (**without** `/v1`, appended automatically). Empty = text-only mode. |
| `NATIVE_MEMORY_EMBEDDING_API_KEY` | _(empty)_ | Yes | Embedding API key. |
| `NATIVE_MEMORY_EMBEDDING_MODEL` | `text-embedding-3-small` | No | Embedding model name. |
| `NATIVE_MEMORY_EMBEDDING_DIMENSIONS` | `1536` | No | Embedding vector dimensions (must match model). Used for auto-creating vector index. |

## Query-Time Relevance Injection (A1)

When enabled, each user message gets top-K relevant memories appended **at write time** (not request time). The block persists with state, so sent bytes == stored history, keeping the provider prompt-cache prefix continuous across turns (KV cache friendly).

| Variable | Default | Description |
|----------|---------|-------------|
| `NATIVE_MEMORY_QUERY_CONTEXT_ENABLED` | `false` | Enable query-time relevance injection. Off by default; enable gradually. |
| `NATIVE_MEMORY_QUERY_CONTEXT_TOP_K` | `3` | Max relevant memories injected per turn. |
| `NATIVE_MEMORY_QUERY_CONTEXT_MAX_CHARS` | `1200` | Injected block char budget. Below minimum renderable size = skip entirely. |

## Self-Evolving Memory

Nightly offline reflection pipeline: distills behavioral lessons (rule/why/how format) from down-rated/failed conversations, stores as `feedback_rule` memories, auto-injects into similar future tasks. Lessons are transparent in the memory panel (view/edit/delete).

| Variable | Default | Description |
|----------|---------|-------------|
| `NATIVE_MEMORY_SELF_EVOLVE_ENABLED` | `false` | Enable self-evolution pipeline (signals → LLM reflection → lessons). |
| `NATIVE_MEMORY_SELF_EVOLVE_MAX_PER_NIGHT` | `3` | Max lessons per user per night. |
| `NATIVE_MEMORY_SELF_EVOLVE_INTERVAL_SECONDS` | `43200` | Scheduler interval in seconds (default 12h). |

Guardrails (borrowed from Codex/Claude Code): writes only via offline pipeline (in-session read-only for lessons), strict schema + sanitization, exclusion rules override user intent, corrections AND positive validations recorded (👍 1/5 sampling anti-drift), 30-day-unrecalled lessons pruned by compaction agent.

## Vector Search Backend

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `NATIVE_MEMORY_VECTOR_BACKEND` | `mongo` | No | Vector search backend: `mongo` (built-in $vectorSearch/cosine fallback) or `qdrant` (dedicated vector DB). |
| `NATIVE_MEMORY_QDRANT_URL` | `http://127.0.0.1:6333` | No | Qdrant server URL. |
| `NATIVE_MEMORY_QDRANT_API_KEY` | _(empty)_ | Yes | Qdrant API key (leave empty if no auth). |

`mongo` mode: MongoDB ≥8.2 natively supports `$vectorSearch` (index auto-created); older versions silently fall back to Python cosine (scans recent 100 docs per query).

`qdrant` mode: MongoDB remains the single source of truth; Qdrant serves as ANN index view only (can be dropped and rebuilt anytime). Supports type/context exact filtering. Any Qdrant failure silently degrades back to mongo pipeline.

## Search & Index

| Variable | Default | Description |
|----------|---------|-------------|
| `NATIVE_MEMORY_INDEX_ENABLED` | `true` | Enable memory search index. |
| `NATIVE_MEMORY_INDEX_CACHE_TTL` | `300` | Index cache TTL in seconds. |
| `NATIVE_MEMORY_APPEND_MAX_DETAILS` | `8` | Maximum details per memory append. |
| `NATIVE_MEMORY_MAX_TOKENS` | `2000` | Maximum tokens for memory content. |
| `NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS` | `1200` | Maximum chars for inline memory content. |

## Reranking

Optional reranking for improved memory relevance.

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `NATIVE_MEMORY_RERANK_MODEL` | _(empty)_ | No | Rerank model name. |
| `NATIVE_MEMORY_RERANK_API_BASE` | _(empty)_ | No | Rerank API base URL. |
| `NATIVE_MEMORY_RERANK_API_KEY` | _(empty)_ | Yes | Rerank API key. |

## Storage & Policy

| Variable | Default | Sensitive | Description |
|----------|---------|-----------|-------------|
| `NATIVE_MEMORY_MODEL` | _(empty)_ | No | Admin model config ID for memory extraction LLM. Empty = default model. |
| `NATIVE_MEMORY_COMPACTION_MODEL_ID` | _(empty)_ | No | Admin model config ID for compaction agent. Empty = default model. |
| `NATIVE_MEMORY_STORE_NAMESPACE` | `memories` | No | LangGraph store namespace. |
| `NATIVE_MEMORY_STALENESS_DAYS` | `30` | No | Days before memory is considered stale. |
| `NATIVE_MEMORY_PRUNE_THRESHOLD` | `90` | No | Prune threshold percentage. |
| `NATIVE_MEMORY_RECALL_MIN_SCORE` | `0.3` | No | Minimum relevance score (0.0-1.0) for recalled memories. |
| `NATIVE_MEMORY_AUTO_COMPACT_ENABLED` | `true` | No | Enable background compaction agent. |
| `NATIVE_MEMORY_AUTO_COMPACT_THRESHOLD` | `40` | No | Per-user count triggering auto-compaction. |
| `NATIVE_MEMORY_AUTO_COMPACT_INTERVAL_SECONDS` | `43200` | No | Periodic scan interval. |
| `NATIVE_MEMORY_AUTO_COMPACT_MIN_INTERVAL_SECONDS` | `900` | No | Cooldown between attempts for same user. |
| `NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY` | `20` | No | Max auto memory evaluations per user per day (0 = unlimited). |

## VFS Working Memory

When `ENABLE_MEMORY_VFS=true`, the `/memories/working/` path is available for agents to store multi-turn task notes (plans, intermediate findings, open hypotheses). Durable user facts must still use the `memory_retain` tool. VFS files are stored in MongoDB (`memories/{user_id}/vfs` namespace), independent of sandbox.

## Production Lighting Sequence

```bash
# 1. Master switch
ENABLE_MEMORY=true

# 2. Embedding (recommended: SiliconFlow bge-m3)
NATIVE_MEMORY_EMBEDDING_API_BASE=https://api.siliconflow.cn
NATIVE_MEMORY_EMBEDDING_API_KEY=sk-your-key
NATIVE_MEMORY_EMBEDDING_MODEL=BAAI/bge-m3
NATIVE_MEMORY_EMBEDDING_DIMENSIONS=1024

# 3. Memory LLM (optional, lightweight channel recommended)
NATIVE_MEMORY_MODEL=glm-5.3-flash

# 4. Query-time injection (enable after observation)
NATIVE_MEMORY_QUERY_CONTEXT_ENABLED=true

# 5. Self-evolution (requires ENABLE_SCHEDULED_TASK=true)
NATIVE_MEMORY_SELF_EVOLVE_ENABLED=true
```

## Example (Full Configuration)

```bash
# Memory + embedding + injection + self-evolution
ENABLE_MEMORY=true
ENABLE_SCHEDULED_TASK=true

# Embedding (SiliconFlow bge-m3)
NATIVE_MEMORY_EMBEDDING_API_BASE=https://api.siliconflow.cn
NATIVE_MEMORY_EMBEDDING_API_KEY=sk-your-key
NATIVE_MEMORY_EMBEDDING_MODEL=BAAI/bge-m3
NATIVE_MEMORY_EMBEDDING_DIMENSIONS=1024

# Memory LLM (existing fast channel)
NATIVE_MEMORY_MODEL=glm-5.3-flash

# Query-time injection
NATIVE_MEMORY_QUERY_CONTEXT_ENABLED=true
NATIVE_MEMORY_QUERY_CONTEXT_TOP_K=3
NATIVE_MEMORY_QUERY_CONTEXT_MAX_CHARS=1200

# Self-evolution
NATIVE_MEMORY_SELF_EVOLVE_ENABLED=true
NATIVE_MEMORY_SELF_EVOLVE_MAX_PER_NIGHT=3
```
