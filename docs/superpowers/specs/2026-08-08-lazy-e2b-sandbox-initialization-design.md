# Lazy E2B Sandbox Initialization Design

## Goal

Remove E2B creation and recovery from the Search Agent's unconditional startup path. A chat turn that never touches the sandbox must reach the model without contacting E2B. The first sandbox-backed operation initializes or reconnects the user's E2B sandbox once, waits for it to become ready, and then executes with the same workspace, environment, storage, and terminal-event guarantees as the current eager path.

The primary success criterion is that a plain Search Agent chat emits its first AI event without waiting for E2B. Based on the observed trace, lazy initialization alone should remove roughly 9 seconds of cold E2B latency from that path. Exact latency remains an observed metric rather than a hard test threshold because model, database, and external-service timing vary.

## Scope

This change covers:

- Search Agent runs when `ENABLE_SANDBOX=true` and `SANDBOX_PLATFORM=e2b`;
- an async lazy backend that satisfies the sandbox operations used by DeepAgents;
- single-flight initialization within one run and continued reuse through `SessionSandboxManager`'s existing per-user cache and lock;
- deterministic E2B session workspace paths before the remote sandbox exists;
- existing sandbox lifecycle events, cancellation, errors, environment variables, skills/memory routes, and artifact roots;
- focused regression tests and timing instrumentation around preparation and lazy initialization.

CubeSandbox, Daytona, Fast Agent, and Team Agent keep their current eager initialization behavior. The new abstraction may be reusable later, but this change will not generalize providers whose workspace cannot be determined safely before connection. It also does not redesign model configuration, MCP loading, graph compilation, or E2B billing/lifecycle settings.

## Current Behavior

`SearchAgent._stream()` builds `SearchAgentContext`, emits metadata, and invokes `agent_node()`. The node resolves the model and store, then `_create_backend_and_prompt()` emits `sandbox:starting` and awaits `SessionSandboxManager.get_or_create()` before it builds the DeepAgent graph or starts the model.

For the observed run, E2B initialization occupied about 9.34 seconds of the roughly 24-second interval before the first visible model content. Even turns that only need a conversational response pay this cost. A failed sandbox also currently fails an otherwise sandbox-free chat.

## Proposed Architecture

### LazyE2BSandboxBackend

Add a run-scoped `LazyE2BSandboxBackend` implementing the async sandbox protocol used by the Search Agent. It is created with:

- `session_id` and `user_id`;
- the deterministic E2B workspace `/home/user/sessions/<safe-session-id>`;
- the current Presenter for lifecycle events;
- a callable that obtains `SessionSandboxManager` only when initialization is required.

The backend has four states: `uninitialized`, `initializing`, `ready`, and `failed`. It stores one initialization task and an async lock. Every async sandbox operation calls `ensure_ready()` and delegates to the resolved E2B backend only after that task succeeds.

The first caller creates the initialization task. Concurrent callers await the same task. They must not create additional E2B sandboxes or emit duplicate lifecycle events. Cross-run and cross-session duplication remains protected by `SessionSandboxManager`'s existing per-user lock and cache.

The lazy backend exposes `work_dir` immediately so DeepAgents can construct its system prompt, `CompositeBackend.artifacts_root`, and middleware without remote I/O. Its pending `id` is an internal placeholder and must not be persisted or emitted as a ready sandbox ID.

The Search Agent runs asynchronously, so lazy initialization is supported through async backend methods. Synchronous methods may delegate after the backend is ready, but they must fail clearly rather than block a running event loop when called before initialization. Tests will prove that the production Search Agent path uses the async methods.

### Search Agent Integration

When sandbox mode is disabled, the existing persistent backend path remains unchanged. When the configured platform is not E2B, the existing eager sandbox path remains unchanged.

For E2B, `_create_backend_and_prompt()` will construct the lazy backend without calling `SessionSandboxManager.get_or_create()`. It will still select `SANDBOX_SYSTEM_PROMPT` and create the same outer `CompositeBackend` routes for `/skills/` and `/memories/`. Because those routes do not use the default backend, reading skills or memory must not initialize E2B.

No `sandbox:starting` event is emitted during agent startup. The first operation routed to the lazy default backend triggers initialization. This includes command execution, file reads and writes, glob/grep/list operations, upload/download, deletion, artifact snapshots, and subagent handoff/activity writes.

### Initialization Sequence

`ensure_ready()` performs this sequence exactly once:

1. Emit `sandbox:starting` through the Presenter.
2. Call `SessionSandboxManager.get_or_create(session_id, user_id)`.
3. Receive the scoped backend only after the manager has created the session work directory and synchronized user environment variables.
4. Validate that the returned backend's `work_dir` equals the deterministic lazy path. A mismatch is an initialization failure; the operation must not run in an unexpected directory.
5. Save the resolved backend as the delegate.
6. Emit `sandbox:ready` with the real sandbox ID and work directory.
7. Execute the original operation against the delegate.

The manager remains the sole owner of provider creation, binding persistence, health checks, and per-user reuse. The lazy wrapper must not duplicate E2B SDK lifecycle logic.

## Observable Semantics

On successful sandbox use, prompts, tools, workspaces, environment variables, tool results, event payloads, trace storage, and final completion remain equivalent to the eager path. Only lifecycle timing changes: `sandbox:starting` and `sandbox:ready` occur immediately before the first sandbox-backed operation instead of before the model starts.

A turn that never invokes the default sandbox backend emits neither sandbox lifecycle event nor any E2B request. It may succeed even when E2B is unavailable. This is an intentional behavior improvement: sandbox availability is required only for work that uses the sandbox.

The Search Agent must continue to advertise the same sandbox tools. Laziness changes resource acquisition, not model capabilities or tool selection.

## Error Handling and Cancellation

If initialization fails, the lazy backend records the exception, emits one `sandbox:error`, and re-raises a sanitized failure. Every waiter receives the same failure; retries within that run do not start another sandbox. The existing task executor converts the propagated failure into the run's normal terminal `error` and `done` handling. No tool result may be emitted for an operation that did not execute.

If the caller is cancelled while awaiting a shared initialization task, cancellation must stop that caller without corrupting the manager cache or cancelling initialization for another waiter. Initialization task ownership and shielding must be explicit. A successfully created sandbox remains in the per-user manager cache for later calls. If provider creation succeeds but binding/work-directory preparation fails, the manager's existing cleanup behavior remains authoritative.

Presenter lifecycle writes must be serialized by the one initialization task. The lazy wrapper will not launch independent event-emission tasks, preventing duplicate or reordered `sandbox:starting`, `sandbox:ready`, and `sandbox:error` events.

## Resource and Concurrency Bounds

The lazy backend holds only one task, one lock, and one resolved delegate. It does not buffer model tokens or tool output. This avoids adding pressure to the already elevated backend memory footprint.

The run-scoped backend provides single-flight behavior inside the run. `SessionSandboxManager` continues to provide the cross-run user lock, so simultaneous sessions for one user may each wait but still converge on one provider sandbox.

## Instrumentation

Add structured duration logs for:

- lazy backend creation, which should perform no provider I/O;
- time from the first sandbox operation to initialization start;
- manager `get_or_create` duration;
- time to ready or failure;
- whether initialization reused a cached/bound sandbox or created a new one when that information is already available without exposing identifiers.

Logs must not include user IDs, sandbox IDs, environment values, credentials, or raw tool arguments. Automated tests assert behavior and ordering, not wall-clock thresholds.

## Testing Strategy

Implementation follows red-green-refactor:

1. Unit tests prove construction performs no manager or provider call and exposes the deterministic work directory.
2. A plain Search Agent graph test proves a model-only response does not initialize E2B and emits no sandbox lifecycle event.
3. Each async backend operation is covered through representative delegation tests; protocol-shape/source coverage ensures no operation bypasses `ensure_ready()`.
4. Concurrent first operations prove one manager call and one `starting`/`ready` pair.
5. Initialization failure proves one `sandbox:error`, identical failure propagation to all waiters, no delegate operation, and no retry within the run.
6. Cancellation tests prove one caller can stop waiting without corrupting another waiter or the eventual cached delegate.
7. Routing tests prove `/skills/` and `/memories/` operations do not initialize E2B, while artifact and subagent backend writes do.
8. Compatibility tests prove disabled sandbox mode and non-E2B providers retain their current paths.
9. Existing Search Agent, E2B backend, session sandbox manager, artifact delivery, subagent middleware, event, cancellation, and task executor tests remain green.

Focused verification will include the changed pytest modules, Ruff on changed Python files, and Mypy or the repository typecheck target where practical. A live smoke test will compare a model-only turn and a sandbox-tool turn. External E2B timing is reported separately from deterministic code verification.

## Deployment and Rollback

The initial implementation is enabled only for Search Agent + E2B and can be guarded by a runtime setting if implementation planning finds that a staged rollout is necessary. Rollback restores the eager `_create_backend_and_prompt()` branch; no database migration or binding rewrite is required.

Existing E2B sandboxes and `user_sandbox_bindings` remain compatible because provider ownership stays in `SessionSandboxManager`. Sandbox templates do not require rebuilding for this Python-only orchestration change.
