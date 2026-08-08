# Unified Lazy Sandbox Initialization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Search Agent initialize E2B, CubeSandbox, or Daytona only on the first sandbox-backed operation while preserving provider behavior, workspace isolation, lifecycle events, artifacts, and cancellation safety.

**Architecture:** Add one run-scoped `LazySandboxBackend` that subclasses DeepAgents `BaseSandbox`, exposes a stable public workspace immediately, and delegates through the existing `SessionSandboxManager` on first use. Search Agent constructs and owns this wrapper without selecting a provider; the manager remains the only provider lifecycle owner. Public file paths map to provider paths at the backend boundary, while shell commands receive a command-scoped `LAMBCHAT_WORKSPACE` and retain the provider backend's real cwd.

**Tech Stack:** Python 3.12, asyncio, FastAPI application services, LangGraph/DeepAgents `BaseSandbox` and `CompositeBackend`, pytest/pytest-asyncio, Ruff, Mypy.

---

## File Structure

- Create `src/infra/backend/lazy_sandbox.py`: lazy state machine, provider delegation, workspace mapping, execution/offload compatibility, lifecycle event attempts, cancellation-safe ownership, and structured timings.
- Modify `src/infra/backend/__init__.py`: export the lazy backend, public error, and public-workspace helper.
- Modify `src/agents/search_agent/context.py`: own and close the run-scoped lazy backend before the Search Agent emits its terminal event.
- Modify `src/agents/search_agent/nodes.py`: replace eager `SessionSandboxManager.get_or_create()` with provider-neutral lazy wrapper construction and registration.
- Modify `src/agents/core/prompt_policy.py` and `src/agents/search_agent/prompt.py`: add Search Agent's lazy-workspace shell/file guidance without changing Team Agent's eager runtime prompt.
- Modify `src/infra/tool/upload_url_tool.py`: resolve a public lazy path before synthesizing a provider-side shell download command. Preserve and reconcile pre-existing user edits in this file.
- Create `tests/infra/backend/test_lazy_sandbox_backend.py`: state, path, protocol, concurrency, cancellation, event, redaction, environment, and offload regression coverage.
- Create `tests/agents/test_search_agent_lazy_sandbox.py`: Search Agent assembly and three-provider no-I/O/first-use behavior.
- Modify `tests/agents/test_agent_context_defaults.py`: run-resource cleanup coverage.
- Modify `tests/agents/core/test_subagent_prompts.py`: lazy Search prompt semantics and eager Team prompt compatibility.
- Modify `tests/infra/tool/test_upload_url_tool.py`: async public-path resolution coverage while retaining existing download/fallback tests.
- Modify `tests/infra/test_session_sandbox_manager.py`: provider-adapter cancellation tests proving late blocking creation is registered or cleaned rather than orphaned.

## Global Constraints

- Preserve all pre-existing uncommitted files and deletions. Never stage or commit an unrelated hunk.
- Do not add provider branches to Search Agent or `LazySandboxBackend`; E2B, CubeSandbox, and Daytona selection stays in `SessionSandboxManager`.
- Do not change Fast Agent or Team Agent eager behavior in this implementation.
- Follow red-green-refactor for every behavior change and record the failing command before production edits.
- Use deterministic provider fakes for required coverage. Run live provider smoke tests only where credentials and infrastructure already exist.

### Task 1: Lazy Backend Construction and Workspace Mapping

**Files:**
- Create: `src/infra/backend/lazy_sandbox.py`
- Create: `tests/infra/backend/test_lazy_sandbox_backend.py`

- [ ] **Step 1: Write failing construction and path tests**

Create fake Presenter, manager factory, provider `BaseSandbox`, and scoped `CompositeBackend` fixtures. Add tests equivalent to:

```python
def test_construction_does_not_obtain_manager() -> None:
    calls = 0

    def manager_factory():
        nonlocal calls
        calls += 1
        raise AssertionError("manager must stay lazy")

    backend = LazySandboxBackend(
        session_id="session / one",
        user_id="user-1",
        presenter=_Presenter(),
        manager_factory=manager_factory,
    )

    assert calls == 0
    assert backend.work_dir == "/workspace/session-one"
    assert isinstance(backend, BaseSandbox)


@pytest.mark.asyncio
async def test_first_file_operation_maps_public_workspace_and_results() -> None:
    provider = _RecordingSandbox(work_dir="/remote/home/sessions/session-1")
    manager = _Manager(provider)
    backend = _lazy(manager, session_id="session-1")

    result = await backend.awrite("/workspace/session-1/report.txt", "ok")

    assert provider.write_calls == [("/remote/home/sessions/session-1/report.txt", "ok")]
    assert result.path == "/workspace/session-1/report.txt"
```

Cover root/descendant mapping, relative paths, segment boundaries (`session-1` versus `session-10`), provider result mapping, and pass-through of explicit external absolute paths.

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```bash
uv run pytest tests/infra/backend/test_lazy_sandbox_backend.py -v
```

Expected: collection fails because `src.infra.backend.lazy_sandbox` does not exist.

- [ ] **Step 3: Implement the minimal type, public workspace helper, and mapping helpers**

In `src/infra/backend/lazy_sandbox.py`, introduce:

```python
PUBLIC_SANDBOX_ROOT = "/workspace"


def public_sandbox_work_dir(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_id).strip(".-")
    return f"{PUBLIC_SANDBOX_ROOT}/{(safe[:80] or 'session')}"


class SandboxInitializationError(RuntimeError):
    PUBLIC_MESSAGE = "Sandbox initialization failed; please retry later"

    def __init__(self) -> None:
        super().__init__(self.PUBLIC_MESSAGE)


class LazySandboxBackend(BaseSandbox):
    def __init__(self, *, session_id, user_id, presenter, manager_factory):
        self._session_id = session_id
        self._user_id = user_id
        self._presenter = presenter
        self._manager_factory = manager_factory
        self._public_work_dir = public_sandbox_work_dir(session_id)
        self._actual_work_dir: str | None = None
        self._delegate: BaseSandbox | None = None
        self._initialization_task: asyncio.Task[BaseSandbox] | None = None
        self._lock = asyncio.Lock()
        self._event_lock = asyncio.Lock()
        self._waiters = 0
        self._closed = False
        self._suppress_events = False

    @property
    def work_dir(self) -> str:
        return self._public_work_dir

    @property
    def id(self) -> str:
        return self._delegate.id if self._delegate is not None else "pending"

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        raise RuntimeError("Lazy sandbox is not initialized; use async operations first")

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        raise RuntimeError("Lazy sandbox is not initialized; use async operations first")

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        raise RuntimeError("Lazy sandbox is not initialized; use async operations first")
```

Add segment-aware `_to_provider_path()` and `_to_public_path()` helpers. The three sync methods above are the minimal abstract-method implementations required to instantiate `BaseSandbox`; Task 3 replaces them with already-ready delegation. Validate manager results only when initialization is added in Task 2; do not call the manager from `__init__`, `work_dir`, or `id`.

- [ ] **Step 4: Implement minimal async file delegation for the first tests**

Add a temporary `_ensure_ready()` skeleton that obtains the manager once and stores `scoped_backend.default` plus returned `work_dir`. Implement `awrite()` with public-to-provider input mapping and provider-to-public result mapping. Keep this step deliberately small; Task 2 completes the protocol and concurrency behavior.

- [ ] **Step 5: Run the focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/backend/test_lazy_sandbox_backend.py -v
```

Expected: construction and initial mapping tests pass.

- [ ] **Step 6: Commit the first vertical slice**

```bash
git add src/infra/backend/lazy_sandbox.py tests/infra/backend/test_lazy_sandbox_backend.py
git commit -m "feat: add provider-neutral lazy sandbox backend"
```

### Task 2: Single-Flight Initialization, Lifecycle Events, and Safe Errors

**Files:**
- Modify: `src/infra/backend/lazy_sandbox.py`
- Modify: `tests/infra/backend/test_lazy_sandbox_backend.py`

- [ ] **Step 1: Write failing single-flight and event-order tests**

Add async tests proving:

- two concurrent first operations call `manager_factory()` and `get_or_create()` once;
- event attempts are exactly `starting`, then `ready` with the real provider ID and actual work directory;
- a `starting` emitter failure does not stop provider initialization or cause a retry;
- a `ready` emitter failure does not turn provider success into failure;
- provider failure attempts one public `sandbox:error` even if `starting` failed;
- every waiter receives `SandboxInitializationError.PUBLIC_MESSAGE` and the same initialization task failure;
- raw provider exception text containing tokens, IDs, and paths is absent from Presenter payloads and captured logs;
- a failed run never starts a second manager request.

Use a gate so both waiters overlap:

```python
release = asyncio.Event()
manager = _Manager(provider, release=release)
first = asyncio.create_task(backend.aread("/workspace/session-1/a.txt"))
second = asyncio.create_task(backend.aread("/workspace/session-1/b.txt"))
await manager.entered.wait()
release.set()
await asyncio.gather(first, second)
assert manager.calls == 1
assert presenter.attempts == ["starting", "ready"]
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run pytest tests/infra/backend/test_lazy_sandbox_backend.py -k "single_flight or event or failure" -v
```

Expected: failures show duplicate/incomplete initialization and missing sanitized error behavior.

- [ ] **Step 3: Implement one owned initialization task**

Implement `_get_initialization_task()` under `asyncio.Lock`, then await it with `asyncio.shield()`. `_initialize()` must:

1. call a shared `_attempt_event()` helper that holds `_event_lock`, re-checks `_suppress_events`, attempts `presenter.emit_sandbox_starting()`, and logs only the emitter exception class if it fails;
2. call `manager_factory().get_or_create(session_id=..., user_id=...)`;
3. validate `CompositeBackend.default` is a `BaseSandbox` and returned `work_dir` is a non-empty absolute POSIX path;
4. store delegate and actual directory;
5. use the same `_attempt_event()` helper for `emit_sandbox_ready(real_id, actual_work_dir)`;
6. on provider failure, use `_attempt_event()` for `emit_sandbox_error(SandboxInitializationError.PUBLIC_MESSAGE)`, log only provider/platform exception categories, and raise `SandboxInitializationError()` from the original exception.

Attach a done callback when the task is created. The callback calls `task.exception()` when not cancelled so an abandoned task cannot produce an unobserved exception warning.

- [ ] **Step 4: Add structured duration logging without identifiers**

Use `time.perf_counter()` and log only operation phase, `settings.SANDBOX_PLATFORM`, duration, and success/reuse information already exposed by manager control flow. Do not log user IDs, sandbox IDs, paths, environment values, credentials, commands, or provider exception strings.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/backend/test_lazy_sandbox_backend.py -k "single_flight or event or failure" -v
```

Expected: all selected tests pass with one manager call and deterministic event attempts.

- [ ] **Step 6: Commit initialization semantics**

```bash
git add src/infra/backend/lazy_sandbox.py tests/infra/backend/test_lazy_sandbox_backend.py
git commit -m "feat: make lazy sandbox initialization single flight"
```

### Task 3: Complete the Sandbox Protocol and Preserve Large-Output Offload

**Files:**
- Modify: `src/infra/backend/lazy_sandbox.py`
- Modify: `tests/infra/backend/test_lazy_sandbox_backend.py`

- [ ] **Step 1: Write failing protocol delegation tests**

Parameterize representative assertions across `als`, `aread`, `agrep`, `aglob`, `awrite`, `aedit`, `adelete`, `aupload_files`, `adownload_files`, and `aexecute`. Add a source/protocol-shape assertion listing every sync/async path-bearing method so a future DeepAgents upgrade cannot silently use an inherited shell fallback.

Add tests proving sync methods:

- raise a clear `RuntimeError` before readiness rather than blocking the running loop;
- delegate normally after one async operation has resolved the provider.

- [ ] **Step 2: Write failing shell isolation and offload tests**

Use two lazy wrappers with different session IDs and one cached provider sandbox. Assert each delegated command begins with a safely quoted, command-local export and neither wrapper mutates `provider.env_vars`:

```python
assert "export LAMBCHAT_WORKSPACE='/remote/a'" in provider.commands[0]
assert "export LAMBCHAT_WORKSPACE='/remote/b'" in provider.commands[1]
assert "LAMBCHAT_WORKSPACE" not in provider.env_vars
```

Instantiate `FilesystemMiddleware` with a `CompositeBackend(default=lazy, artifacts_root=lazy.work_dir)` and drive `aexecute_with_offload()`. Prove for E2B-, CubeSandbox-, and Daytona-shaped fake delegates that:

- `isinstance(lazy, BaseSandbox)` keeps capture-at-source enabled;
- the delegate receives the actual capture path and the command-scoped workspace prefix;
- the tool message points to the public `/workspace/<session>/large_tool_results/...` path;
- `aread(public_capture_path)` reads the captured content;
- delegate-specific `enable_capture_offload=False` remains respected without rerunning the command.

- [ ] **Step 3: Run protocol/offload tests and verify RED**

Run:

```bash
uv run pytest tests/infra/backend/test_lazy_sandbox_backend.py -k "protocol or workspace_env or offload or sync" -v
```

Expected: missing methods or inherited fallback behavior fail.

- [ ] **Step 4: Implement every protocol method explicitly**

Follow the path translation pattern already used by `WorkflowScopedBackend` in `src/infra/backend/deepagent.py`, but delegate to the resolved provider `BaseSandbox`. Map path-bearing result fields back to public paths. Preserve non-path fields such as pagination, `truncated`, `occurrences`, content, errors, sizes, and timestamps.

Implement `_require_ready_delegate()` for synchronous calls. Do not use `run_until_complete`, `asyncio.run`, or thread-blocking initialization from sync methods.

- [ ] **Step 5: Implement command-scoped shell injection and offload overrides**

Build only a controlled prefix:

```python
def _with_workspace_env(self, command: str) -> str:
    actual = shlex.quote(self._require_actual_work_dir())
    return f"export LAMBCHAT_WORKSPACE={actual}; {command}"
```

Do not parse or replace user command text. `aexecute_with_offload()` must await readiness, map `capture_path`, prefix `command`, and call the delegate's own `aexecute_with_offload()` so provider capture behavior is preserved. Implement the sync equivalent only for the already-ready state.

- [ ] **Step 6: Run the complete backend test file and verify GREEN**

Run:

```bash
uv run pytest tests/infra/backend/test_lazy_sandbox_backend.py -v
```

Expected: all lazy backend tests pass.

- [ ] **Step 7: Commit protocol compatibility**

```bash
git add src/infra/backend/lazy_sandbox.py tests/infra/backend/test_lazy_sandbox_backend.py
git commit -m "feat: preserve sandbox protocol and output offload"
```

### Task 4: Cancellation-Safe Ownership and Provider Completion

**Files:**
- Modify: `src/infra/backend/lazy_sandbox.py`
- Modify: `tests/infra/backend/test_lazy_sandbox_backend.py`
- Modify: `tests/infra/test_session_sandbox_manager.py`

- [ ] **Step 1: Write failing waiter-cancellation tests**

Add tests for:

- cancelling one of two waiters leaves initialization alive and the other waiter succeeds;
- cancelling the sole waiter marks the wrapper closed/abandoned, suppresses late ready/error events, and prevents another operation in that run from creating a second request;
- `aclose()` before initialization performs no manager I/O;
- `aclose()` during initialization returns without cancelling the shielded manager task, and its done callback consumes the eventual outcome.
- an event emitter paused after acquiring the event lock must finish before `aclose()` returns, while an event waiting to acquire the lock is suppressed after close; therefore no lifecycle event can complete after close returns.

- [ ] **Step 2: Write failing provider blocking-create tests**

In `tests/infra/test_session_sandbox_manager.py`, parameterize the existing E2B, CubeSandbox, and Daytona adapter fakes. Pause each provider at its blocking create call, cancel/close the sole lazy waiter, release provider creation, then assert one of the manager's existing authoritative outcomes:

- successful creation is saved in the platform-scoped binding and manager cache; or
- a post-create preparation failure runs the provider helper's existing cleanup and does not leave an unbound live object.

Also assert no late Presenter event is attempted after close. Do not add provider lifecycle code to the lazy wrapper to make the test pass.

- [ ] **Step 3: Run cancellation tests and verify RED**

Run:

```bash
uv run pytest tests/infra/backend/test_lazy_sandbox_backend.py -k cancel -v
uv run pytest tests/infra/test_session_sandbox_manager.py -k "cancel and create" -v
```

Expected: cancellation currently propagates to or loses ownership of the initialization task.

- [ ] **Step 4: Implement waiter accounting, abandonment, and close**

Around `await asyncio.shield(task)`, increment/decrement `_waiters` under the state lock. When cancellation leaves zero waiters:

- set `_closed=True` and `_suppress_events=True`;
- do not cancel `_initialization_task`;
- do not await the provider operation from `aclose()`;
- reject later operations in the same wrapper with a stable closed/cancelled error;
- allow manager `get_or_create()` to finish binding/caching or cleaning its resource.

All lifecycle attempts must use `_attempt_event()`, which owns `_event_lock` across both the suppression check and awaited Presenter call. `aclose()` acquires the same lock before setting `_suppress_events=True` and `_closed=True`; consequently it waits for an already-started emission to finish and prevents any later emission from starting. Starting may already have completed before cancellation, but no ready/error event can complete after `aclose()` returns.

- [ ] **Step 5: Run cancellation and session-manager tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/backend/test_lazy_sandbox_backend.py -k cancel -v
uv run pytest tests/infra/test_session_sandbox_manager.py -k "cancel and create" -v
```

Expected: all selected tests pass and no `Task exception was never retrieved` warning appears.

- [ ] **Step 6: Commit cancellation safety**

```bash
git add src/infra/backend/lazy_sandbox.py tests/infra/backend/test_lazy_sandbox_backend.py tests/infra/test_session_sandbox_manager.py
git commit -m "fix: keep lazy sandbox creation cancellation safe"
```

### Task 5: Integrate Lazy Initialization into Search Agent

**Files:**
- Modify: `src/infra/backend/__init__.py`
- Modify: `src/agents/search_agent/context.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/core/prompt_policy.py`
- Modify: `src/agents/search_agent/prompt.py`
- Create: `tests/agents/test_search_agent_lazy_sandbox.py`
- Modify: `tests/agents/test_agent_context_defaults.py`
- Modify: `tests/agents/core/test_subagent_prompts.py`

- [ ] **Step 1: Write failing Search Agent assembly tests**

Parameterize `SANDBOX_PLATFORM` as `e2b`, `cubesandbox`, and `daytona`. Patch `get_session_sandbox_manager` to raise if called during `_create_backend_and_prompt()`, patch `acreate_store`, and assert:

```python
backend, prompt, store, lazy, work_dir = await _create_backend_and_prompt(...)

assert isinstance(lazy, LazySandboxBackend)
assert backend.default is lazy
assert backend.artifacts_root == work_dir == "/workspace/session-1"
assert presenter.sandbox_events == []
```

Then invoke one lazy file or execute operation and assert the manager is obtained only then, with one ordered event pair for every configured provider. Add a disabled-sandbox case proving the persistent backend branch is unchanged.

Add routing tests using the actual outer `CompositeBackend`: reads/writes under `/skills/` and `/memories/` must not initialize the lazy default, while artifact-root writes, artifact snapshots, and subagent handoff writes must initialize it exactly once.

- [ ] **Step 2: Write failing context cleanup and prompt tests**

Add a fake closeable lazy resource to `SearchAgentContext`, call `context.close()`, and assert it closes once and clears the reference. Cover repeated close.

Add prompt assertions:

- Search Agent lazy runtime section names the public file-tool workspace;
- shell guidance requires relative paths or `$LAMBCHAT_WORKSPACE` and forbids using the public alias literally in shell commands;
- Team Agent continues using the existing eager `SANDBOX_RUNTIME_POLICY` with its real `{work_dir}`.

- [ ] **Step 3: Write graph-level model-only and first-tool tests before production changes**

Exercise `SearchAgent._stream()` so the test covers the real outer graph, `agent_node()`, a real DeepAgents inner graph, middleware construction, and `SearchAgentContext.close()` before terminal `done`. Use a deterministic fake chat model:

- model-only response: the fake manager raises if obtained; assert the first/final AI content succeeds, no lifecycle event is attempted, `context.close()` closes an uninitialized wrapper, and close occurs before `done`;
- first-tool response: the fake model emits a real `write_file` or `execute` tool call followed by a final answer; assert any streamed AI content before the tool is processed first, then one `starting`/`ready` pair, one manager request, correct public/actual path mapping, and unchanged final answer;
- capture the `create_deep_agent()` arguments or inspect the compiled graph to prove main/subagent middleware and artifact roots receive the public workspace without initialization;
- fail the test if any sync lazy method is called before readiness.

Use the fake `BaseChatModel` patterns in `tests/agents/core/test_nested_graph_context.py` and `tests/infra/agent/test_artifact_delivery_middleware.py`. Do not replace either graph with a stub that bypasses DeepAgents middleware.

- [ ] **Step 4: Run Search Agent tests and verify RED**

Run:

```bash
uv run pytest tests/agents/test_search_agent_lazy_sandbox.py tests/agents/test_agent_context_defaults.py tests/agents/core/test_subagent_prompts.py -v
```

Expected: Search Agent still initializes the manager eagerly, model-only graph execution reaches the manager, and context owns no sandbox resource.

- [ ] **Step 5: Export and assemble the lazy backend**

Export `LazySandboxBackend`, `SandboxInitializationError`, and `public_sandbox_work_dir` from `src/infra/backend/__init__.py`.

In `_create_backend_and_prompt()`:

- retain the authenticated-user guard;
- generate/reuse one `session_id` value;
- construct `LazySandboxBackend(..., manager_factory=get_session_sandbox_manager)` without invoking the factory or checking platform;
- register it on `SearchAgentContext`;
- pass it directly to `create_sandbox_backend()`;
- return the lazy wrapper and its public `work_dir` for middleware truthiness/path configuration;
- remove eager starting/ready/error emission from this function.

Do not add E2B/CubeSandbox/Daytona branches.

- [ ] **Step 6: Add context-owned finalization**

Add a typed optional lazy-backend field and a small `set_sandbox_resource()` method to `SearchAgentContext`. Its idempotent `close()` awaits `resource.aclose()` before returning. `SearchAgent._stream()` already calls `await context.close()` in `finally` before yielding `done`; keep that ordering and prove it in the test rather than adding another cleanup path to `agent_node()`.

- [ ] **Step 7: Add a lazy-only runtime prompt section**

Keep `SANDBOX_RUNTIME_POLICY` unchanged for eager Team/Fast paths. Add `LAZY_SANDBOX_RUNTIME_POLICY` in `src/agents/core/prompt_policy.py`, and make Search Agent's `SANDBOX_RUNTIME_SECTION` alias it. The section must clearly separate:

- file tools: use `{work_dir}` as the absolute public workspace;
- shell: starts in the real session workspace, so use relative paths or `$LAMBCHAT_WORKSPACE`;
- do not insert the public alias literally into shell commands.

- [ ] **Step 8: Run assembly, graph, cleanup, and prompt tests and verify GREEN**

Run:

```bash
uv run pytest tests/agents/test_search_agent_lazy_sandbox.py tests/agents/test_agent_context_defaults.py tests/agents/core/test_subagent_prompts.py -v
```

Expected: all three providers share the lazy branch, model-only graph execution emits no sandbox event, first-tool graph execution initializes once, and context cleanup precedes terminal `done`.

- [ ] **Step 9: Commit Search Agent integration**

```bash
git add src/infra/backend/__init__.py src/agents/search_agent/context.py src/agents/search_agent/nodes.py src/agents/core/prompt_policy.py src/agents/search_agent/prompt.py tests/agents/test_search_agent_lazy_sandbox.py tests/agents/test_agent_context_defaults.py tests/agents/core/test_subagent_prompts.py
git commit -m "feat: initialize Search Agent sandbox on first use"
```

### Task 6: Resolve Public Paths in URL Downloads

**Files:**
- Modify: `src/infra/tool/upload_url_tool.py`
- Modify: `tests/infra/tool/test_upload_url_tool.py`

> Before editing, inspect and preserve the existing uncommitted user changes. Apply a narrow patch around `_execute_sandbox_download`; do not replace or reformat unrelated tool-schema work. `src/infra/tool/upload_url_tool.py` already has user-owned edits, so only the new resolver hunk may be staged.

- [ ] **Step 1: Write the failing async path-resolution test**

Add a real outer `CompositeBackend(routes={}, default=lazy)` whose `default` is either the real `LazySandboxBackend` with a fake manager/provider or a protocol-complete `BaseSandbox` fake with `aresolve_path()`:

```python
class _ResolvingLazyBackend(BaseSandbox):
    async def aresolve_path(self, path: str) -> str:
        assert path == "/workspace/session-1/input.txt"
        return "/remote/session-1/input.txt"

    async def aexecute(self, command: str):
        self.command = command
        return SimpleNamespace(exit_code=0, output="")

    # Implement id, execute, upload_files, and download_files so the fake
    # satisfies BaseSandbox/SandboxBackendProtocol and CompositeBackend.aexecute().
```

Pass `CompositeBackend(default=lazy, routes={})` through the runtime exactly as Search Agent does. Assert the shell command contains only the resolved actual destination, while the tool's JSON result continues returning the caller-visible public path. Add compatibility tests for a direct resolving backend and for a backend with no resolver.

- [ ] **Step 2: Run upload tests and verify RED**

Run:

```bash
uv run pytest tests/infra/tool/test_upload_url_tool.py -k "resolve or prefers_sandbox_side" -v
```

Expected: the command still embeds the public path.

- [ ] **Step 3: Implement the narrow resolution hook**

In `_execute_sandbox_download()`, find the resolver on the runtime backend first and then on its default backend before building the command:

```python
resolved_path = file_path
resolver = getattr(backend, "aresolve_path", None)
if not callable(resolver):
    resolver = getattr(getattr(backend, "default", None), "aresolve_path", None)
if callable(resolver):
    resolved_path = await resolver(file_path)
command = _sandbox_download_command(url, resolved_path)
```

Do not expose `resolved_path` in logs or returned JSON. Let `SandboxInitializationError` propagate to the existing tool error boundary with only its fixed public message.

- [ ] **Step 4: Run the full upload tool test file and verify GREEN**

Run:

```bash
uv run pytest tests/infra/tool/test_upload_url_tool.py -v
```

Expected: all existing streaming, size-limit, blocking-IO, and new path-resolution tests pass.

- [ ] **Step 5: Stage only the bridge hunk and inspect ownership**

```bash
git add tests/infra/tool/test_upload_url_tool.py
git add -p -- src/infra/tool/upload_url_tool.py
git diff --cached -- src/infra/tool/upload_url_tool.py tests/infra/tool/test_upload_url_tool.py
```

Accept only the resolver lines. If Git cannot split the hunk cleanly from user-owned edits, unstage this source file and leave the source plus its new test uncommitted for the final handoff; do not stage the entire file and do not manufacture a mixed-ownership commit.

- [ ] **Step 6: Commit only if the staged diff is ownership-clean**

```bash
git commit -m "fix: resolve lazy sandbox paths for URL downloads"
```

If the resolver source hunk cannot be isolated, skip this commit and report the verified uncommitted change explicitly at handoff.

### Task 7: Cross-Provider Regression and Final Verification

**Files:**
- Modify only if a failing focused test proves necessary: provider backend or helper files under `src/infra/backend/` and `src/infra/sandbox/`
- Test: all files changed in Tasks 1-6

- [ ] **Step 1: Run the focused lazy sandbox suite**

Run:

```bash
uv run pytest \
  tests/infra/backend/test_lazy_sandbox_backend.py \
  tests/agents/test_search_agent_lazy_sandbox.py \
  tests/agents/test_agent_context_defaults.py \
  tests/agents/core/test_subagent_prompts.py \
  tests/infra/tool/test_upload_url_tool.py \
  tests/infra/test_session_sandbox_manager.py \
  tests/infra/backend/test_deepagent_backend_factory.py \
  tests/infra/backend/test_deepagents_protocol_compat.py \
  tests/infra/agent/test_artifact_delivery_middleware.py \
  tests/infra/agent/test_main_agent_context_middleware.py \
  tests/infra/agent/test_subagent_activity_middleware.py \
  -v
```

Expected: all selected tests pass.

- [ ] **Step 2: Run lint and type checking for changed Python code**

Run:

```bash
uv run ruff check \
  src/infra/backend/lazy_sandbox.py \
  src/infra/backend/__init__.py \
  src/agents/search_agent/context.py \
  src/agents/search_agent/nodes.py \
  src/agents/core/prompt_policy.py \
  src/agents/search_agent/prompt.py \
  src/infra/tool/upload_url_tool.py \
  tests/infra/backend/test_lazy_sandbox_backend.py \
  tests/agents/test_search_agent_lazy_sandbox.py \
  tests/infra/tool/test_upload_url_tool.py
uv run mypy src/infra/backend/lazy_sandbox.py src/agents/search_agent/context.py src/agents/search_agent/nodes.py src/infra/tool/upload_url_tool.py
```

Expected: zero Ruff errors and zero Mypy errors. If repository-wide Mypy includes known unrelated failures, capture them separately and keep the changed-file run green.

- [ ] **Step 3: Verify no eager provider call remains in Search Agent**

Run:

```bash
rg -n "get_or_create|emit_sandbox_starting|emit_sandbox_ready|emit_sandbox_error|SANDBOX_PLATFORM" src/agents/search_agent src/infra/backend/lazy_sandbox.py
```

Expected: Search Agent contains no direct `get_or_create()` await or platform branch; lifecycle calls and the deferred manager call live only in `lazy_sandbox.py`.

- [ ] **Step 4: Run model-only and first-tool smoke tests where credentials exist**

For each locally configured provider (`e2b`, `cubesandbox`, `daytona`):

1. run a plain Search Agent turn and record that first AI content precedes any sandbox request and no sandbox lifecycle event is stored;
2. run a turn that executes `pwd` and writes/reads a file;
3. verify one `starting`/`ready` pair, correct file content, actual `ready.work_dir`, and no duplicate sandbox creation;
4. verify `pwd` equals the provider session directory and `$LAMBCHAT_WORKSPACE` matches it.

Do not mark unavailable provider smoke tests as passed; report them as unrun external checks with deterministic mocked coverage.

- [ ] **Step 5: Review the final diff for user-change preservation**

Run:

```bash
git status --short
git diff --check
git diff -- src/infra/tool/upload_url_tool.py tests/infra/tool/test_upload_url_tool.py
```

Expected: no whitespace errors; the upload files retain all pre-existing user edits plus only the planned path-resolution change.

- [ ] **Step 6: Commit any test-only integration adjustments**

If Task 7 required tracked changes:

```bash
git add <only-files-changed-for-task-7>
git commit -m "test: verify unified lazy sandbox initialization"
```

If no files changed, do not create an empty commit.
