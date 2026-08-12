# Chat First-Token and MCP Refresh Design

**Date:** 2026-08-13

**Status:** Approved direction (option 1)

**Scope:** Search, Fast, and Team chat startup paths; global MCP cache; first real thinking delivery

## Problem

The inspected Search Agent session `25cc5944-2fc4-49fb-8932-0f05448052d5`
shows two distinct latency classes:

| Phase | First observed turn | Following warm turns |
| --- | ---: | ---: |
| User event to metadata | 4.40s | 1.42-2.12s |
| Metadata to inner LangGraph | 9.25s | 1.91-2.04s |
| Inner LangGraph to first thinking | 1.85s | 1.04-1.51s |
| User event to first thinking | 15.50s | 4.40-5.67s |

The raw provider log and persisted trace agree within milliseconds. For example,
provider reasoning arrived at `23:59:05.380` and the `thinking` event was recorded
at `23:59:05.382`. The thinking stream is therefore not being held by the
200-character continuation buffer: the existing first-chunk fast path works.

The global MCP cache has a separate foreground-latency defect. Its 900-second
TTL is measured from `created_at`, and an expired entry is synchronously rebuilt
on the next chat turn even when a usable initialized manager is still present.
The existing MCP warmup implementation is not scheduled by application startup.
A current read-only discovery of this user's two MCP servers took about 547ms,
so MCP is a real avoidable contributor but does not explain every second of the
observed pre-model delay.

## Goals

- Never make a chat turn synchronously refresh an otherwise usable MCP catalog
  merely because its TTL elapsed.
- Keep explicit MCP configuration, policy, role, and preference invalidation
  immediate and authoritative.
- Warm recently active users' MCP catalogs after process startup without
  blocking application readiness.
- Run independent agent preparation work concurrently so the model starts as
  soon as all required inputs are ready.
- Preserve the current behavior that emits the first non-empty provider
  reasoning chunk immediately.
- Add safe phase evidence so future first-token regressions can be attributed
  to task setup, MCP, agent preparation, provider TTFT, or event delivery.
- Under comparable model and network conditions, target a warm first-thinking
  time around 2-3 seconds. This is an operational target, not a correctness
  guarantee, because provider TTFT and reasoning duration are external.

## Non-goals

- Do not fabricate thinking text or emit private chain-of-thought that the
  provider did not return.
- Do not reduce configured thinking intensity automatically.
- Do not change MCP tool-call semantics, quotas, role checks, or retry policy.
- Do not persist secrets, MCP URLs, headers, tool arguments, user messages, or
  provider exception bodies in timing logs.
- Do not build the larger persistent serialized MCP-tool catalog in this change.

## Design

### 1. Stale-while-revalidate global MCP cache

`get_global_mcp_tools(user_id)` will distinguish four states:

- **Fresh:** return the initialized entry immediately.
- **Stale:** return the initialized entry immediately and schedule one bounded
  background refresh for that user.
- **Refreshing:** return the current initialized entry; do not create a second
  refresh.
- **Missing or explicitly invalidated:** perform the existing single-flight
  foreground initialization because no safe catalog exists.

Background refresh creates a new manager without mutating the visible entry.
After successful tool discovery it atomically swaps the new entry under the
existing per-user lock, then closes the replaced manager outside the foreground
path. Refresh failure keeps the stale entry usable and applies a short retry
cooldown so repeated chat turns cannot hammer an unavailable MCP server.

Explicit invalidation remains a hard boundary. A per-user generation counter is
captured when refresh begins and incremented by local or Pub/Sub invalidation.
If the generation changed before swap, the newly built manager is closed and is
not installed. This prevents a late background refresh from resurrecting config
that the user or administrator just removed.

Refresh tasks use the module's existing background-task tracking and are drained
on shutdown. Cache and refresh logs contain only stable fields such as
`cache_status`, `duration_ms`, `server_count`, `tool_count`, and `result`.

### 2. Bounded startup warmup for recently active users

Application startup will schedule MCP warmup as a background task after runtime
listeners are ready. Startup readiness will not await it.

The warmup selector will use recent trace activity rather than an arbitrary user
collection order, deduplicate user IDs, and retain the existing configured user
and concurrency caps. Users without enabled MCP servers complete cheaply. The
task is tracked on `app.state`, cancelled/drained during shutdown, and failures
remain isolated per user.

This reduces process-restart cold misses while avoiding an unbounded connection
storm. A genuinely new user with no prior warmup may still pay one cold discovery;
all later TTL refreshes use stale-while-revalidate.

### 3. Concurrent task and agent preparation

The direct-submit path already persists `user:message` and creates its trace
before the background executor starts. When the executor receives that explicit
`user_message_written` contract together with the same trace ID, its Presenter
will adopt the existing trace instead of running a second trace creation and
user-identity lookup. Recovery and queued paths that cannot prove pre-creation
retain the current `_ensure_trace()` behavior.

After the session enters `STARTING`, heartbeat startup and the transition to
`RUNNING` are independent and will run together. Both must finish before agent
execution begins, preserving cancellation, concurrency, and status semantics
while removing avoidable serialized storage waits.

After the request-scoped context has completed setup, the following independent
work will begin together where each agent path supports it:

- model object resolution;
- backend/store construction (the Search sandbox remains lazy);
- MCP/tool catalog retrieval and disabled-tool filtering;
- skills prompt construction;
- checkpointer retrieval.

The code awaits the group before compiling the inner agent graph. No model call
starts until the final allowed tool set, prompt sections, backend, and
checkpointer are available, so tool visibility and authorization semantics do
not change.

Search and Fast nodes will use the same preparation pattern. Team inherits the
Fast context and receives the same MCP cache behavior; its node will only adopt
the concurrency change where its dependencies are equivalent. Preparation
exceptions retain their current fail-open or fail-closed behavior rather than
being silently converted.

The three independent disabled-MCP preference queries will also run concurrently.
They preserve the same union result and existing fail-open behavior.

### 4. First-thinking delivery

No production buffering change is required for the first real thinking chunk.
The `TextChunkBuffer` first append already flushes immediately, Presenter writes
the event directly to Redis, and the frontend applies `thinking` synchronously
to message state.

Regression coverage will lock in this contract across the boundaries:

1. the first non-empty reasoning chunk emits one `thinking` event immediately;
2. later small chunks may still batch to control write/render overhead;
3. a first text chunk flushes pending thinking before text;
4. the frontend renders the first `thinking` SSE event without waiting for a
   second event or a size threshold.

No placeholder thinking content will be introduced. Moving actual provider start
earlier is the latency improvement.

### 5. Safe first-event phase timing

Normal application logs will record monotonic durations for stable phases:

- `task_prepare`;
- `context_setup`;
- `agent_prepare`;
- `mcp_cache` with `fresh`, `stale`, `refresh`, or `cold` status;
- `provider_first_delta`;
- `provider_first_reasoning`;
- `provider_first_text`.

Only the first occurrence of each provider milestone is recorded per run. The
existing trace/request context provides correlation; timing messages will not
copy content, IDs into metric names, URLs, headers, tool schemas, or exception
bodies.

## Failure and cancellation behavior

- Stale refresh failure leaves the previous initialized entry available.
- Cold initialization retains current failure isolation: one bad MCP server does
  not prevent successfully discovered tools from other servers.
- Explicit invalidation wins over every in-flight refresh.
- Startup warmup failure never prevents the API from becoming ready.
- Cancelling a chat does not close the shared global MCP manager.
- Application shutdown drains refresh/warmup tasks and closes installed managers
  once.

## Testing strategy

### MCP cache tests

- A stale entry returns before a gated refresh manager is released.
- Concurrent stale callers create exactly one refresh.
- Successful refresh atomically replaces the entry and closes the old manager.
- Failed refresh retains the stale entry and respects retry cooldown.
- Invalidation during refresh prevents late stale installation.
- Shutdown drains or cancels refresh tasks without leaking managers.
- Startup warmup is scheduled without delaying lifespan startup and respects
  recent-user, maximum-user, and concurrency bounds.

### Preparation tests

- A pre-persisted trace is adopted without a second create call; an unproven
  trace still uses `_ensure_trace()`.
- Heartbeat startup and the `RUNNING` status transition begin concurrently and
  both complete before agent execution.
- Gated dependencies prove independent preparation operations have all started
  before any one is released.
- The final graph receives the same filtered tools, prompt sections, backend,
  and checkpointer as the sequential path.
- Search, Fast, and applicable Team paths retain their existing error behavior.

### Streaming tests

- Backend processor tests cover immediate first reasoning, continuation batching,
  and thinking-before-text ordering.
- Frontend event tests assert that one `thinking` event immediately creates or
  updates the visible thinking part.

### Verification

- Run focused MCP, Search/Fast/Team preparation, event processor, and frontend
  event tests.
- Run Ruff on changed Python files, targeted Mypy, frontend lint for changed
  TypeScript, and the relevant production builds where frontend code changes.
- Re-measure a cold-start turn, a warm turn, and an expired-cache turn with the
  same model. The expired-cache turn must not contain a foreground MCP refresh
  gap; provider-to-Presenter first-thinking overhead must remain in the
  millisecond range.

## Acceptance criteria

- An expired but initialized MCP entry does not block chat on network discovery.
- Explicit config invalidation cannot be undone by a late refresh.
- At most one refresh runs per user per process.
- Startup warmup is bounded and non-blocking.
- Direct-submit task preparation avoids duplicate trace creation and overlaps
  independent heartbeat/status work without changing terminal state behavior.
- Independent agent preparation is concurrent without changing the final tool
  set or authorization result.
- The first real reasoning chunk is emitted and rendered immediately.
- Timing logs can distinguish foreground setup, MCP state, provider TTFT, first
  reasoning, and first text without exposing sensitive values.
- In a comparable warmed local run, first-thinking latency is materially lower
  than the observed 4.40-5.67 second baseline; the operational target is roughly
  2-3 seconds when provider TTFT remains near the observed 1.0-1.5 seconds.
