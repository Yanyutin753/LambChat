# Unified Lazy Sandbox Initialization Design

## Goal

Remove sandbox creation, recovery, and session-directory preparation from the Search Agent's unconditional startup path. A turn that never touches sandbox-backed storage or execution must reach the model without contacting E2B, CubeSandbox, or Daytona. The first sandbox-backed operation initializes the configured provider once, then executes with the same environment, storage, lifecycle, and artifact guarantees as the current eager path.

The primary success criterion is that a plain Search Agent chat emits its first AI event without waiting for a sandbox provider. In the observed E2B trace, this should remove roughly 9 seconds of cold sandbox latency from the model-only path. Exact latency remains an observed metric rather than a hard test threshold because database, provider, and model timing vary.

## Scope

This change covers:

- Search Agent runs when `ENABLE_SANDBOX=true` for all supported `SANDBOX_PLATFORM` values: `e2b`, `cubesandbox`, and `daytona`;
- one provider-neutral async lazy backend satisfying the sandbox operations used by DeepAgents;
- single-flight initialization within one run and continued reuse through `SessionSandboxManager`'s existing per-user cache and lock;
- a stable public session workspace path before the provider's actual work directory is known;
- safe mapping between that public path and each provider's real session work directory;
- existing lifecycle events, cancellation, errors, environment synchronization, skills/memory routes, artifact roots, and subagent handoffs;
- focused regression tests and timing instrumentation around lazy initialization.

Fast Agent and Team Agent remain eager in this change. The lazy backend is intentionally provider-neutral so those agents can adopt it separately, but changing every agent at once would increase the regression surface without being required to improve Search Agent first-event latency. This change does not redesign model configuration, MCP loading, graph compilation, provider billing, or provider pause/resume policies.

## Current Behavior

`SearchAgent._stream()` builds `SearchAgentContext`, emits metadata, and invokes `agent_node()`. The node resolves the model and store, then `_create_backend_and_prompt()` emits `sandbox:starting` and awaits `SessionSandboxManager.get_or_create()` before it builds the DeepAgent graph or starts the model.

For the observed run, E2B initialization occupied about 9.34 seconds of the roughly 24-second interval before the first visible model content. Even turns that only need a conversational response pay this cost. A provider outage also currently fails an otherwise sandbox-free chat. CubeSandbox and Daytona follow the same eager Search Agent control flow, even though their internal connection and work-directory behavior differ.

## Proposed Architecture

### LazySandboxBackend

Add a run-scoped `LazySandboxBackend` subclassing DeepAgents `BaseSandbox`. Subclassing, rather than only structurally implementing `SandboxBackendProtocol`, preserves `FilesystemMiddleware`'s `isinstance(BaseSandbox)` capability detection for capture-at-source large-output offload. It is created with:

- `session_id` and `user_id`;
- a stable public workspace such as `/workspace/<safe-session-id>`;
- the current Presenter for lifecycle events;
- a callable that obtains `SessionSandboxManager` only when initialization is required.

The wrapper contains no E2B, CubeSandbox, or Daytona SDK logic and performs no platform branch. `SessionSandboxManager` remains the only component that selects a provider and owns creation, binding persistence, health checks, recovery, environment synchronization, and per-user reuse.

The backend has four states: `uninitialized`, `initializing`, `ready`, and `failed`. It stores one initialization task and an async lock. Every async sandbox operation calls `ensure_ready()` and delegates only after that task succeeds. The first caller creates the initialization task; concurrent callers await the same task. They must not create additional sandboxes or emit duplicate lifecycle events.

The wrapper exposes its public `work_dir` immediately so DeepAgents can build `CompositeBackend.artifacts_root`, prompts, artifact middleware, and subagent handoff paths without provider I/O. A pending `id` is an internal placeholder and must never be persisted or emitted as a ready sandbox ID.

The wrapper overrides all path-bearing sync and async operations rather than inheriting `BaseSandbox` file fallbacks, because inherited fallbacks would embed public paths directly into shell commands. It also overrides `execute_with_offload()` and `aexecute_with_offload()`: after readiness, it maps the capture path to the actual provider workspace and delegates to the resolved provider's `BaseSandbox` offload implementation. The middleware still reports the public capture path, and later reads map that public path back to the actual capture file. The lazy wrapper advertises capture offload only when the resolved delegate supports it; the async first-use path must retain the current provider's offload behavior rather than silently falling back to generic truncation.

The Search Agent runs asynchronously, so first-use initialization is supported through async backend methods. Synchronous methods may delegate after the backend is ready, but must fail clearly rather than block a running event loop when called before initialization. Tests will prove that Search Agent's production path uses async methods before readiness.

### Public and Provider Workspace Paths

The public workspace is stable across providers and is the only pre-initialization absolute path exposed to DeepAgents. After initialization, the wrapper stores the actual `work_dir` returned by `SessionSandboxManager` and maps sandbox file-operation paths at the boundary:

- the public workspace root maps to the provider session root;
- descendants map by preserving their relative suffix;
- relative paths resolve inside the provider session root;
- provider results are mapped back to public paths before reaching the model or middleware;
- absolute paths outside the public workspace pass through unchanged for compatibility with existing provider files and explicit user paths.

The mapping applies to list, read, write, edit, delete, glob, grep, upload, and download operations. It must use segment-aware prefix checks, not string replacement, so `/workspace/session-1` cannot match `/workspace/session-10`.

Shell command strings are not searched or rewritten because parsing arbitrary shell syntax is unsafe. The resolved provider session root remains the command working directory through the existing provider backends. For every `execute` call, the lazy wrapper prepends a shell-quoted, command-scoped `LAMBCHAT_WORKSPACE=<actual-work-dir>` assignment/export before delegating. This controlled prefix overrides a same-named user environment variable for that command only; it must not mutate the cached backend's `env_vars`, provider-global environment, or shared sandbox state. Two concurrent session wrappers sharing one user sandbox therefore retain different command cwd/workspace values without racing.

Prompt text instructs the model to use relative paths or `$LAMBCHAT_WORKSPACE` for shell commands while using the public absolute path for file tools. Tools that synthesize shell commands from file paths, including `upload_url_to_sandbox`, must resolve the path through a narrow async backend path-resolution hook before building the command. This avoids embedding an unusable public path in provider-side shell commands.

No provider is required to create the public `/workspace/...` path or a root-level symlink. E2B and CubeSandbox may continue using `/home/user/...`; Daytona may continue returning its remote work directory. Existing real absolute paths are not migrated or rewritten.

### Search Agent Integration

When sandbox mode is disabled, the existing persistent backend path remains unchanged. When sandbox mode is enabled, `_create_backend_and_prompt()` always constructs the same provider-neutral lazy wrapper without creating `SessionSandboxManager` or checking `SANDBOX_PLATFORM`. It then builds the existing outer `CompositeBackend` routes for `/skills/` and `/memories/` and returns immediately.

No `sandbox:starting` event is emitted during agent startup. The first operation routed to the lazy default backend triggers initialization. This includes command execution, sandbox file operations, uploads/downloads, artifact snapshots, and subagent handoff/activity writes. Operations routed entirely to `/skills/` or `/memories/` do not initialize a sandbox.

The sandbox prompt is adjusted to distinguish the public file-tool root from shell cwd semantics. Sandbox capabilities and tool availability remain unchanged; only resource acquisition timing changes.

### Initialization Sequence

`ensure_ready()` performs this sequence exactly once:

1. Emit `sandbox:starting` through the Presenter.
2. Obtain the singleton `SessionSandboxManager` and call `get_or_create(session_id, user_id)`.
3. Receive the scoped composite backend and actual work directory only after the manager has created the session directory and synchronized user environment variables.
4. Validate that the returned default backend is executable and that the returned work directory is a non-empty absolute path.
5. Store the resolved default backend and actual work directory as the delegate and path-mapping target.
6. Attempt to emit `sandbox:ready` with the real sandbox ID and actual work directory, preserving the existing event payload contract.
7. Execute the original operation against the delegate.

The manager's existing provider-specific code remains unchanged unless a focused compatibility fix is proven necessary by tests. The lazy wrapper must not duplicate SDK lifecycle logic or infer a provider work directory.

## Observable Semantics

For E2B, CubeSandbox, and Daytona, a Search Agent turn that never invokes the lazy default backend:

- emits neither `sandbox:starting` nor `sandbox:ready`;
- makes no sandbox manager or provider request;
- may succeed even when the configured provider is unavailable.

On first sandbox use, all three providers attempt one ordered `sandbox:starting` then `sandbox:ready` pair before the first operation result. Subsequent operations in the run reuse the resolved delegate. Prompts, environment variables, tools, skills/memory routes, artifacts, and terminal completion remain functionally equivalent to the eager path. Only lifecycle timing changes; the ready payload retains the current provider ID and actual work directory.

If the model produces content before deciding to call a sandbox tool, that content may precede `sandbox:starting`. This interleaving is intentional and does not change the final answer or tool results.

## Error Handling and Cancellation

If initialization fails, the lazy backend stores an internal `SandboxInitializationError` whose public message is the fixed, provider-neutral `Sandbox initialization failed; please retry later`. The original exception is chained as the cause for controlled diagnostics, but its raw message, credentials, identifiers, and paths are never included in Presenter events or user-visible tool output. Logs use the existing redaction facilities and exception category rather than interpolating the raw provider exception. Every waiter receives the same public failure; retries within that run do not start another sandbox. No tool result may claim that an operation executed when initialization failed.

A caller cancelled while awaiting shared initialization stops waiting without cancelling the shared task when another live waiter exists. The wrapper counts active waiters. If cancellation leaves no waiter, it marks initialization abandoned, suppresses later lifecycle events, cancels and gathers its owned task, and transitions to a terminal cancelled state so another operation in that run cannot start a second provider request. Cancellation of a thread-backed SDK call may not stop the remote request immediately; any resource that still completes is owned by the manager's cache/cleanup policy, but it cannot emit `sandbox:ready` or `sandbox:error` after the run's terminal event.

The Search Agent owns the run-scoped wrapper and closes it from its cancellation/finalization path before emitting terminal completion. Closing marks the wrapper event-suppressed and cancels/gathers an in-flight initialization when it has no remaining waiter. A successfully created sandbox remains in the manager cache for later runs. If provider creation succeeds but binding, work-directory preparation, or environment synchronization fails, the manager's current provider-specific cleanup behavior remains authoritative.

Lifecycle writes are serialized by the one initialization task. The exactly-once guarantee means exactly one ordered **attempt** for each applicable event: emitter failure is logged in redacted form and is not retried, does not replace a successful provider result, and does not prevent the next applicable lifecycle attempt. A provider failure causes one `sandbox:error` attempt even if `sandbox:starting` emission failed. The wrapper never launches independent event-emission tasks, preventing duplicate or reordered attempts.

## Resource and Concurrency Bounds

The lazy backend holds one task, one lock, one resolved delegate, and two workspace path strings. It does not buffer model tokens or tool output. The run-scoped wrapper provides single-flight behavior inside the run. `SessionSandboxManager` continues to provide its cross-run per-user lock, so simultaneous sessions for one user may wait but still converge on one provider sandbox.

## Instrumentation

Add structured duration logs for:

- lazy wrapper creation, which must perform no provider I/O;
- time from the first sandbox operation to initialization start;
- manager `get_or_create` duration;
- time to ready or failure;
- configured provider name and whether the manager reused or created a sandbox when already available from existing control flow.

Logs must not include user IDs, sandbox IDs, environment values, credentials, public or actual workspace paths, or raw tool arguments. Automated tests assert behavior and ordering, not wall-clock thresholds.

## Testing Strategy

Implementation follows red-green-refactor:

1. Construction tests prove no manager/provider call occurs and the public workspace is stable and shell-safe.
2. A model-only Search Agent graph test is parameterized for E2B, CubeSandbox, and Daytona; it proves no initialization and no lifecycle event.
3. A first-use graph test for each provider proves the manager is called only after a sandbox operation begins and emits one ordered `starting`/`ready` pair.
4. Representative async protocol tests cover execute and every path-bearing operation; protocol-shape/source coverage ensures no method bypasses `ensure_ready()` or path mapping. A large-output test for each provider proves `BaseSandbox` detection remains active, capture occurs at the actual path, the returned pointer uses the public artifact path, and that pointer is readable through the wrapper.
5. Workspace tests cover public-to-actual and actual-to-public mapping, relative paths, segment boundaries, external absolute paths, shell cwd/environment behavior, and `upload_url_to_sandbox` resolution. A two-session concurrency test proves command-scoped `LAMBCHAT_WORKSPACE` and cwd do not leak across wrappers sharing one cached user sandbox and do not mutate user environment state.
6. Concurrent first operations prove one manager call and one lifecycle-event sequence.
7. Initialization failure proves one `sandbox:error`, identical failure propagation to all waiters, no delegate operation, and no retry within the run.
8. Cancellation tests cover both cases: one caller stops waiting while another receives the eventual delegate; and the sole remaining caller is cancelled, causing task gathering and event suppression before terminal completion with no late ready/error event.
9. Routing tests prove `/skills/` and `/memories/` do not initialize a sandbox, while artifact snapshots and subagent backend writes do.
10. Emitter-failure tests prove lifecycle attempts are not retried, provider success/failure remains authoritative, and public errors/log assertions contain no provider messages, secrets, IDs, or paths.
11. Compatibility tests prove disabled sandbox mode remains unchanged and the three providers use one lazy Search Agent branch with no provider-specific eager fallback.
12. Existing Search Agent, provider backend, session manager, artifact delivery, subagent middleware, event, cancellation, and task executor tests remain green.

Focused verification includes changed pytest modules, Ruff on changed Python files, and Mypy or the repository typecheck target where practical. Live smoke tests compare a model-only turn and a sandbox-tool turn for each available provider. A provider unavailable in the local environment is covered deterministically with its adapter mocked and reported as an unrun external smoke test.

## Deployment and Rollback

The initial implementation applies to Search Agent for E2B, CubeSandbox, and Daytona together; there is no provider-specific rollout branch. If a runtime guard is needed, it gates unified Search Agent laziness rather than individual providers. Rollback restores eager `_create_backend_and_prompt()` behavior for all three providers.

No database migration or binding rewrite is required. Existing provider sandboxes and platform-scoped `user_sandbox_bindings` remain compatible because ownership stays in `SessionSandboxManager`. Sandbox templates and snapshots do not require rebuilding for this Python-only orchestration change.
