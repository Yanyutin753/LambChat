# Background Artifact Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move automatic sandbox snapshots and artifact reveal/upload work off the main Agent tool-call critical path while preserving artifact display before terminal `done`.

**Architecture:** `ArtifactDeliveryMiddleware` will own a per-run set of tracked background tasks, a four-slot delivery semaphore, per-path generation state, and a three-second terminal drain. Direct file tools schedule delivery after returning their real result; `execute` schedules paired snapshot/diff work; `aafter_agent` drains and cancels any remainder before the event stream can emit `done`.

**Tech Stack:** Python 3.12, asyncio, LangChain `AgentMiddleware`, pytest, pytest-asyncio, Ruff.

## Global Constraints

- Automatic work for `execute`, `write_file`, `edit_file`, and `upload_url_to_sandbox` must not delay the originating tool result.
- Explicit `reveal_file` and `reveal_project` remain foreground operations.
- Reveal/upload concurrency is exactly four operations per active Agent invocation.
- Terminal drain timeout is exactly three seconds.
- No artifact task may emit after terminal drain returns.
- Existing artifact payloads, filters, descriptions, priorities, changed-file cap, and middleware registration remain unchanged.
- Preserve all unrelated dirty work in the checkout; stage only files named by each task.

---

## File Map

- Modify `src/infra/agent/middleware/artifact_delivery.py`: own tracked tasks, background delivery coordination, snapshot scheduling, deduplication, and terminal drain.
- Modify `tests/infra/agent/test_artifact_delivery_middleware.py`: add behavioral regressions for non-blocking tools, concurrency, deduplication, failure isolation, and cancellation; update existing timing assumptions.
- Reference only `docs/superpowers/specs/2026-08-08-background-artifact-delivery-design.md`: approved behavior and non-goals.

No new production module is needed: the middleware keeps a private coordinator for each active Agent invocation, keyed by the invocation's stable LangGraph stream writer.

---

### Task 1: Tracked background delivery for direct file tools

**Files:**
- Modify: `tests/infra/agent/test_artifact_delivery_middleware.py:480-789`
- Modify: `src/infra/agent/middleware/artifact_delivery.py:5-24,241-299,394-414,508-555`

**Interfaces:**
- Consumes: existing `StagedArtifact`, `_stage_path()`, `_deliver_artifact()`, and presenter lookup.
- Produces: `_track_background_task(awaitable: Awaitable[Any], *, name: str) -> asyncio.Task[Any] | None`, `_schedule_artifact_delivery(artifact: StagedArtifact, runtime: Any, *, allow_without_presenter: bool = False) -> None`, `_deliver_latest_artifact(normalized_path: str, runtime: Any) -> None`, and `_drain_background_tasks() -> None`.

- [ ] **Step 1: Add a presenter test double and a failing non-blocking direct-tool test**

Add this test utility near the existing backend fakes:

```python
class RecordingPresenter:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)

    def present_artifact_result(
        self,
        artifact,
        *,
        success=True,
        error=None,
        depth=0,
        agent_id=None,
    ):
        return {
            "event": "artifact:result",
            "data": {
                "artifact": artifact,
                "success": success,
                "error": error,
                "depth": depth,
                "agent_id": agent_id,
            },
        }
```

Add a parameterized test with literal cases so removing scheduling for any direct tool fails:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "tool_args", "content", "expected_path"),
    [
        (
            "write_file",
            {"file_path": "/workspace/report.md", "content": "# Report"},
            "ok",
            "/workspace/report.md",
        ),
        (
            "edit_file",
            {"path": "/workspace/report.md", "old_string": "a", "new_string": "b"},
            "updated",
            "/workspace/report.md",
        ),
        (
            "upload_url_to_sandbox",
            {"url": "https://cdn.example.com/input.png"},
            json.dumps({"success": True, "path": "/workspace/input.png"}),
            "/workspace/input.png",
        ),
    ],
)
async def test_direct_artifact_tools_return_before_background_reveal(
    tool_name: str,
    tool_args: dict[str, str],
    content: str,
    expected_path: str,
) -> None:
    reveal_started = asyncio.Event()
    release_reveal = asyncio.Event()
    presenter = RecordingPresenter()

    async def blocked_reveal(**kwargs):
        assert kwargs["file_path"] == expected_path
        reveal_started.set()
        await release_reveal.wait()
        return json.dumps({"_meta": {"path": expected_path}})

    middleware = ArtifactDeliveryMiddleware(reveal_file=blocked_reveal)
    runtime = SimpleNamespace(config={"configurable": {"presenter": presenter}})

    async def handler(_request):
        return ToolMessage(content=content, tool_call_id="tool-1", name=tool_name)

    result = await asyncio.wait_for(
        middleware.awrap_tool_call(
            SimpleNamespace(
                tool_call={"name": tool_name, "id": "tool-1", "args": tool_args},
                runtime=runtime,
            ),
            handler,
        ),
        timeout=1.0,
    )

    assert result.content == content
    await asyncio.wait_for(reveal_started.wait(), timeout=1.0)
    assert presenter.events == []

    release_reveal.set()
    await middleware.aafter_agent({"messages": []}, runtime)
    assert [event["event"] for event in presenter.events] == ["artifact:result"]
```

Production mutation caught: restoring `await self._deliver_staged_artifacts(...)` in the wrapper makes `wait_for` time out.

- [ ] **Step 2: Run the direct-tool test and verify RED**

Run:

```bash
uv run pytest tests/infra/agent/test_artifact_delivery_middleware.py::test_direct_artifact_tools_return_before_background_reveal -q
```

Expected: all three cases fail with `TimeoutError` because current code waits for `blocked_reveal`.

- [ ] **Step 3: Add tracked task state and direct delivery scheduling**

Import `asyncio` and `contextlib`, add constants, and initialize invocation-scoped state:

```python
_ARTIFACT_DELIVERY_CONCURRENCY = 4
_ARTIFACT_BACKGROUND_DRAIN_TIMEOUT = 3.0

# in __init__
self._background_tasks: set[asyncio.Task[Any]] = set()
self._delivery_tasks: dict[str, asyncio.Task[Any]] = {}
self._artifact_generations: dict[str, int] = {}
self._delivery_semaphore = asyncio.Semaphore(_ARTIFACT_DELIVERY_CONCURRENCY)
self._background_closed = False
```

Implement task tracking. Read the timeout constant when draining rather than binding it as a default argument, so the cancellation test can shorten it safely:

```python
def _track_background_task(
    self,
    awaitable: Awaitable[Any],
    *,
    name: str,
) -> asyncio.Task[Any] | None:
    if self._background_closed:
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()
        return None

    task = asyncio.create_task(awaitable, name=f"artifact:{name}")
    self._background_tasks.add(task)

    def on_done(done_task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(done_task)
        if done_task.cancelled():
            return
        try:
            done_task.result()
        except Exception:
            logger.warning("Artifact background task failed: %s", name, exc_info=True)

    task.add_done_callback(on_done)
    return task
```

Implement normalized-path coalescing with generation checks:

```python
def _schedule_artifact_delivery(
    self,
    artifact: StagedArtifact,
    runtime: Any,
    *,
    allow_without_presenter: bool = False,
) -> None:
    if self._get_presenter(runtime) is None and not allow_without_presenter:
        return
    normalized = _normalize_path(artifact.path)
    active = self._delivery_tasks.get(normalized)
    if active is not None and not active.done():
        return
    task = self._track_background_task(
        self._deliver_latest_artifact(normalized, runtime),
        name=f"deliver:{normalized}",
    )
    if task is not None:
        self._delivery_tasks[normalized] = task

async def _deliver_latest_artifact(self, normalized: str, runtime: Any) -> None:
    current_task = asyncio.current_task()
    try:
        while True:
            artifact = self._artifacts.get(normalized)
            if artifact is None or artifact.revealed:
                return
            generation = self._artifact_generations.get(normalized, 0)
            async with self._delivery_semaphore:
                delivered = await self._deliver_artifact(artifact, runtime)
            if generation != self._artifact_generations.get(normalized, 0):
                continue
            if delivered:
                artifact.revealed = True
            return
    finally:
        if self._delivery_tasks.get(normalized) is current_task:
            self._delivery_tasks.pop(normalized, None)
```

Increment `self._artifact_generations[normalized_path]` inside `_stage_path()` whenever that method replaces the current artifact. Scheduling an already-staged artifact must not increment its generation; otherwise `aafter_agent()` would turn every in-flight delivery into a duplicate second delivery.

Change `_deliver_staged_artifacts()` into a synchronous scheduler and remove inline awaits from direct-tool handling:

```python
def _deliver_staged_artifacts(self, artifacts: list[StagedArtifact], runtime: Any) -> None:
    for artifact in artifacts:
        if not artifact.revealed:
            self._schedule_artifact_delivery(artifact, runtime)
```

In `awrap_tool_call()`, keep explicit reveal branches unchanged, but call the scheduler and return the original `ToolMessage` immediately for direct file tools.

Implement a drain loop that includes child delivery tasks created by an in-flight snapshot task:

```python
async def _drain_background_tasks(self) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _ARTIFACT_BACKGROUND_DRAIN_TIMEOUT
    while self._background_tasks:
        remaining = deadline - loop.time()
        if remaining <= 0:
            break
        done, _ = await asyncio.wait(list(self._background_tasks), timeout=remaining)
        self._background_tasks.difference_update(done)

    self._background_closed = True
    pending = list(self._background_tasks)
    for task in pending:
        task.cancel()
    if pending:
        logger.warning(
            "Cancelling %s artifact background task(s) after %.1fs drain timeout",
            len(pending),
            _ARTIFACT_BACKGROUND_DRAIN_TIMEOUT,
        )
        await asyncio.gather(*pending, return_exceptions=True)
```

Update `aafter_agent()` to schedule all pending artifacts with `allow_without_presenter=True`, always drain snapshot tasks even when no artifact is pending yet, and return `{"messages": []}` only when the artifact map is non-empty after the drain:

```python
async def aafter_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
    self._auto_stage_external_urls_from_state(state)
    for artifact in self._artifacts.values():
        if not artifact.revealed:
            self._schedule_artifact_delivery(
                artifact,
                runtime,
                allow_without_presenter=True,
            )
    await self._drain_background_tasks()
    return {"messages": []} if self._artifacts else None
```

This preserves no-presenter reveal/file-library side effects without performing the same reveal twice.

- [ ] **Step 4: Run direct-tool and existing direct-artifact tests and verify GREEN**

Run:

```bash
uv run pytest \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_direct_artifact_tools_return_before_background_reveal \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_artifact_delivery_emits_artifact_when_write_file_finishes \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_artifact_delivery_auto_stages_successful_write_file \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_artifact_delivery_auto_stages_successful_edit_file \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_artifact_delivery_auto_stages_successful_upload_url_to_sandbox -q
```

Expected: PASS with no un-awaited coroutine or pending-task warnings.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/infra/agent/middleware/artifact_delivery.py tests/infra/agent/test_artifact_delivery_middleware.py
git commit -m "perf: background direct artifact delivery"
```

---

### Task 2: Background workspace snapshot and execute diff pipeline

**Files:**
- Modify: `tests/infra/agent/test_artifact_delivery_middleware.py:14-55,791-923`
- Modify: `src/infra/agent/middleware/artifact_delivery.py:254-299,416-478`

**Interfaces:**
- Consumes: Task 1 `_track_background_task()`, `_deliver_staged_artifacts()`, and `_drain_background_tasks()`.
- Produces: `abefore_agent(state: Any, runtime: Any) -> None`, `_schedule_workspace_snapshot(runtime: Any, *, name: str) -> asyncio.Task[Any] | None`, and `_process_execute_changes(runtime: Any, before_task: asyncio.Task[Any] | None, result: ToolMessage) -> None`.

- [ ] **Step 1: Add a controllable snapshot backend and failing execute latency test**

Add a backend fake that mirrors the complete `GlobResult` boundary and blocks only the post-command snapshot:

```python
class BlockingAfterSnapshotBackend:
    def __init__(self) -> None:
        self.calls = 0
        self.after_started = asyncio.Event()
        self.release_after = asyncio.Event()

    async def aglob(self, pattern: str, path: str = "/") -> GlobResult:
        assert pattern == "**/*"
        assert path == "/workspace"
        self.calls += 1
        if self.calls == 1:
            return GlobResult(
                matches=[{"path": "/workspace/existing.txt", "size": 1, "modified_at": "1"}]
            )
        self.after_started.set()
        await self.release_after.wait()
        return GlobResult(
            matches=[
                {"path": "/workspace/existing.txt", "size": 1, "modified_at": "1"},
                {"path": "/workspace/report.csv", "size": 12, "modified_at": "2"},
            ]
        )
```

Add the regression:

```python
@pytest.mark.asyncio
async def test_execute_returns_before_background_post_snapshot() -> None:
    backend = BlockingAfterSnapshotBackend()
    presenter = RecordingPresenter()
    reveal_paths: list[str] = []

    async def reveal_file(**kwargs):
        reveal_paths.append(kwargs["file_path"])
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(
        reveal_file=reveal_file,
        workspace_path="/workspace",
    )
    runtime = SimpleNamespace(
        config={"configurable": {"backend": backend, "presenter": presenter}}
    )

    async def handler(_request):
        return ToolMessage(content="created report.csv", tool_call_id="exec-1", name="execute")

    result = await asyncio.wait_for(
        middleware.awrap_tool_call(
            SimpleNamespace(
                tool_call={"name": "execute", "id": "exec-1", "args": {"command": "build"}},
                runtime=runtime,
            ),
            handler,
        ),
        timeout=1.0,
    )
    assert result.content == "created report.csv"

    await asyncio.wait_for(backend.after_started.wait(), timeout=1.0)
    assert reveal_paths == []
    backend.release_after.set()
    await middleware.aafter_agent({"messages": []}, runtime)
    assert reveal_paths == ["/workspace/report.csv"]
```

Production mutation caught: awaiting `_auto_stage_execute_changes()` in the wrapper makes the first `wait_for` time out.

- [ ] **Step 2: Run the execute latency test and verify RED**

Run:

```bash
uv run pytest tests/infra/agent/test_artifact_delivery_middleware.py::test_execute_returns_before_background_post_snapshot -q
```

Expected: FAIL with `TimeoutError` because current execute handling awaits the second snapshot.

- [ ] **Step 3: Schedule baseline, paired snapshots, diffing, and delivery**

Initialize snapshot state:

```python
self._snapshot_lock = asyncio.Lock()
self._baseline_snapshot_task: asyncio.Task[Any] | None = None
self._last_snapshot: dict[str, tuple[int | None, str | None]] | None = None
```

Start the best-effort baseline without awaiting it:

```python
async def abefore_agent(self, state: Any, runtime: Any) -> None:
    del state
    if self._baseline_snapshot_task is None:
        self._baseline_snapshot_task = self._schedule_workspace_snapshot(
            runtime,
            name="initial-snapshot",
        )
```

Serialize automatic snapshot requests without putting their I/O on the caller's stack:

```python
async def _take_workspace_snapshot(self, runtime: Any):
    async with self._snapshot_lock:
        snapshot = await self._snapshot_workspace(runtime)
        if snapshot is not None:
            self._last_snapshot = snapshot
        return snapshot

def _schedule_workspace_snapshot(self, runtime: Any, *, name: str):
    return self._track_background_task(
        self._take_workspace_snapshot(runtime),
        name=name,
    )
```

At `execute` entry, schedule `before_task` before awaiting the real handler. On a successful `ToolMessage`, schedule `_process_execute_changes(...)` and return the real result immediately. The pipeline must:

```python
async def _process_execute_changes(self, runtime, before_task, result) -> None:
    if getattr(result, "status", None) == "error":
        return
    parsed = _parse_jsonish(result.content)
    if isinstance(parsed, dict) and (
        parsed.get("success") is False or parsed.get("error") is not None
    ):
        return

    before_snapshot = None
    if before_task is not None:
        with contextlib.suppress(Exception):
            before_snapshot = await before_task
    if before_snapshot is None and self._baseline_snapshot_task is not None:
        with contextlib.suppress(Exception):
            before_snapshot = await self._baseline_snapshot_task
    if before_snapshot is None:
        before_snapshot = self._last_snapshot

    after_snapshot = await self._take_workspace_snapshot(runtime)
    if before_snapshot is None or after_snapshot is None:
        return

    staged = self._stage_snapshot_changes(before_snapshot, after_snapshot)
    self._deliver_staged_artifacts(staged, runtime)
```

Extract the existing pure diff loop into `_stage_snapshot_changes(before_snapshot, after_snapshot) -> list[StagedArtifact]`, retaining the limit, filters, description, and priority exactly.

- [ ] **Step 4: Run execute snapshot regressions and verify GREEN**

Run:

```bash
uv run pytest \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_execute_returns_before_background_post_snapshot \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_artifact_delivery_auto_stages_files_created_by_execute \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_artifact_delivery_auto_stages_files_modified_by_execute \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_artifact_delivery_execute_snapshot_skips_ignored_outputs \
  tests/infra/agent/test_artifact_delivery_middleware.py::test_artifact_snapshot_is_unavailable_when_glob_returns_error -q
```

Expected: PASS. Update old tests only to drain through `aafter_agent`; do not weaken their literal path and call assertions.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/infra/agent/middleware/artifact_delivery.py tests/infra/agent/test_artifact_delivery_middleware.py
git commit -m "perf: background execute artifact snapshots"
```

---

### Task 3: Concurrent delivery, same-path coalescing, and terminal cancellation

**Files:**
- Modify: `tests/infra/agent/test_artifact_delivery_middleware.py:480-1040`
- Modify: `src/infra/agent/middleware/artifact_delivery.py:238-620`

**Interfaces:**
- Consumes: Tasks 1-2 background task, delivery, snapshot, and drain methods.
- Produces: final concurrency, generation, exception isolation, and no-post-`done` lifecycle behavior.

- [ ] **Step 1: Add failing concurrency and generation tests**

Add a test where four real `write_file` paths enter reveal concurrently while a fifth remains behind the semaphore:

```python
@pytest.mark.asyncio
async def test_distinct_artifacts_reveal_concurrently() -> None:
    started: set[str] = set()
    four_started = asyncio.Event()
    release = asyncio.Event()
    presenter = RecordingPresenter()

    async def blocked_reveal(**kwargs):
        started.add(kwargs["file_path"])
        if len(started) == 4:
            four_started.set()
        await release.wait()
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(reveal_file=blocked_reveal)
    runtime = SimpleNamespace(config={"configurable": {"presenter": presenter}})

    async def run_write(path: str, call_id: str) -> None:
        async def handler(_request):
            return ToolMessage(content="ok", tool_call_id=call_id, name="write_file")
        await middleware.awrap_tool_call(
            SimpleNamespace(
                tool_call={
                    "name": "write_file",
                    "id": call_id,
                    "args": {"file_path": path, "content": path},
                },
                runtime=runtime,
            ),
            handler,
        )

    paths = [f"/workspace/{name}.txt" for name in ("a", "b", "c", "d", "e")]
    await asyncio.gather(*(run_write(path, f"write-{index}") for index, path in enumerate(paths)))
    await asyncio.wait_for(four_started.wait(), timeout=1.0)
    await asyncio.sleep(0)
    assert len(started) == 4
    release.set()
    await middleware.aafter_agent({"messages": []}, runtime)
    assert started == set(paths)
```

Add a same-path test that stages a second write while the first reveal is in flight and asserts exactly two generations are delivered, never two concurrent deliveries for that path:

```python
@pytest.mark.asyncio
async def test_same_path_write_coalesces_to_one_delivery_worker() -> None:
    calls: list[str] = []
    active = 0
    max_active = 0
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    presenter = RecordingPresenter()

    async def reveal_file(**kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        calls.append(kwargs["file_path"])
        if len(calls) == 1:
            first_started.set()
            await release_first.wait()
        active -= 1
        return json.dumps({"_meta": {"path": kwargs["file_path"]}})

    middleware = ArtifactDeliveryMiddleware(reveal_file=reveal_file)
    runtime = SimpleNamespace(config={"configurable": {"presenter": presenter}})

    async def run_write(content: str, call_id: str) -> None:
        async def handler(_request):
            return ToolMessage(content="ok", tool_call_id=call_id, name="write_file")
        await middleware.awrap_tool_call(
            SimpleNamespace(
                tool_call={
                    "name": "write_file",
                    "id": call_id,
                    "args": {"file_path": "/workspace/report.md", "content": content},
                },
                runtime=runtime,
            ),
            handler,
        )

    await run_write("first", "write-1")
    await first_started.wait()
    await run_write("second", "write-2")
    release_first.set()
    await middleware.aafter_agent({"messages": []}, runtime)

    assert calls == ["/workspace/report.md", "/workspace/report.md"]
    assert max_active == 1
```

Production mutations caught: restoring a serial loop prevents `four_started`; removing generation checks emits a stale duplicate or loses the second generation.

- [ ] **Step 2: Add failing terminal timeout and failure-isolation tests**

Shorten the module constant with `monkeypatch`, block reveal forever, call `aafter_agent()`, then release the event after it returns and assert no presenter event appears:

```python
@pytest.mark.asyncio
async def test_terminal_drain_cancels_work_before_done(monkeypatch) -> None:
    monkeypatch.setattr(artifact_delivery, "_ARTIFACT_BACKGROUND_DRAIN_TIMEOUT", 0.01)
    reveal_started = asyncio.Event()
    never_release = asyncio.Event()
    presenter = RecordingPresenter()

    async def blocked_reveal(**_kwargs):
        reveal_started.set()
        await never_release.wait()
        return "{}"

    middleware = ArtifactDeliveryMiddleware(reveal_file=blocked_reveal)
    runtime = SimpleNamespace(config={"configurable": {"presenter": presenter}})

    async def handler(_request):
        return ToolMessage(content="ok", tool_call_id="write-1", name="write_file")

    result = await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {"file_path": "/workspace/slow.pdf", "content": "pdf"},
            },
            runtime=runtime,
        ),
        handler,
    )
    assert result.content == "ok"
    await reveal_started.wait()

    await middleware.aafter_agent({"messages": []}, runtime)
    never_release.set()
    await asyncio.sleep(0)
    assert presenter.events == []
```

Import the module for constant patching:

```python
from src.infra.agent.middleware import artifact_delivery
```

Add a public-wrapper failure test:

```python
@pytest.mark.asyncio
async def test_background_reveal_failure_does_not_fail_write_tool() -> None:
    presenter = RecordingPresenter()

    async def failing_reveal(**_kwargs):
        raise RuntimeError("storage offline")

    middleware = ArtifactDeliveryMiddleware(reveal_file=failing_reveal)
    runtime = SimpleNamespace(config={"configurable": {"presenter": presenter}})

    async def handler(_request):
        return ToolMessage(content="ok", tool_call_id="write-1", name="write_file")

    result = await middleware.awrap_tool_call(
        SimpleNamespace(
            tool_call={
                "name": "write_file",
                "id": "write-1",
                "args": {"file_path": "/workspace/report.pdf", "content": "pdf"},
            },
            runtime=runtime,
        ),
        handler,
    )
    await middleware.aafter_agent({"messages": []}, runtime)

    assert result.content == "ok"
    assert presenter.events[0]["event"] == "artifact:result"
    assert presenter.events[0]["data"]["success"] is False
    assert presenter.events[0]["data"]["error"] == "storage offline"
```

- [ ] **Step 3: Run the new lifecycle tests and verify RED where behavior is still missing**

Run:

```bash
uv run pytest tests/infra/agent/test_artifact_delivery_middleware.py \
  -k 'concurrently or generation or terminal_drain or background_failure' -q
```

Expected before the final implementation: at least the concurrency or generation test fails if Task 1's minimal implementation did not yet cover its contract. Confirm each failure names the missing behavior, not a fixture error.

- [ ] **Step 4: Complete concurrency, coalescing, and cancellation behavior**

Replace the Task 1 delivery worker with this final version:

```python
async def _deliver_latest_artifact(self, normalized: str, runtime: Any) -> None:
    current_task = asyncio.current_task()
    try:
        while True:
            artifact = self._artifacts.get(normalized)
            if artifact is None or artifact.revealed:
                return
            generation = self._artifact_generations.get(normalized, 0)
            async with self._delivery_semaphore:
                delivered = await self._deliver_artifact(artifact, runtime)
            if generation != self._artifact_generations.get(normalized, 0):
                continue
            if delivered:
                artifact.revealed = True
            return
    finally:
        if self._delivery_tasks.get(normalized) is current_task:
            self._delivery_tasks.pop(normalized, None)
```

Keep the following invariants in the surrounding scheduler and drain code:

- every reveal is inside `async with self._delivery_semaphore`;
- `_delivery_tasks[normalized]` contains at most one live task;
- generation changes cause the live worker loop to deliver the latest artifact once more;
- `CancelledError` is re-raised, not logged as an ordinary failure;
- `_drain_background_tasks()` loops until descendants finish or the shared deadline expires;
- timeout cancellation gathers every task and clears delivery-task bookkeeping through worker `finally` blocks;
- scheduling after close closes the coroutine and creates no task;
- reveal exceptions keep `_deliver_artifact()`'s failed-event behavior and never escape to the tool wrapper.

Do not add retry policy, persistent queues, frontend state, or new configuration.

- [ ] **Step 5: Run the full artifact middleware suite and verify GREEN**

Run:

```bash
uv run pytest tests/infra/agent/test_artifact_delivery_middleware.py -q
```

Expected: all tests pass with no `Task was destroyed`, `Task exception was never retrieved`, or un-awaited coroutine warnings.

- [ ] **Step 6: Run related agent middleware regressions**

Run:

```bash
uv run pytest \
  tests/agents/test_team_agent_sandbox_support.py \
  tests/infra/agent/test_events_processor.py \
  tests/infra/agent/test_main_agent_context_middleware.py -q
```

Expected: PASS.

- [ ] **Step 7: Run Ruff on the changed Python files**

Run:

```bash
uv run ruff check \
  src/infra/agent/middleware/artifact_delivery.py \
  tests/infra/agent/test_artifact_delivery_middleware.py
uv run ruff format --check \
  src/infra/agent/middleware/artifact_delivery.py \
  tests/infra/agent/test_artifact_delivery_middleware.py
```

Expected: both commands exit zero.

- [ ] **Step 8: Commit Task 3**

```bash
git add src/infra/agent/middleware/artifact_delivery.py tests/infra/agent/test_artifact_delivery_middleware.py
git commit -m "fix: bound background artifact lifecycle"
```

---

## Final Verification

- [ ] Confirm `git diff --check 60e9aa78..HEAD -- src/infra/agent/middleware/artifact_delivery.py tests/infra/agent/test_artifact_delivery_middleware.py` reports no whitespace errors for the implementation commits.
- [ ] Confirm `git status --short` shows only the user's pre-existing unrelated changes and no untracked artifact-delivery files.
- [ ] Review the mutation targets: inline await restored, one direct tool omitted, semaphore removed, generation comparison removed, cancellation omitted, explicit reveal backgrounded. Every mutation must be caught by at least one named test above.
- [ ] Report focused test counts, related regression counts, Ruff results, and the unchanged dirty-worktree caveat.
