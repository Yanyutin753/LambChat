# Chat First-Token and MCP Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove foreground MCP TTL refreshes, overlap independent startup work, and preserve immediate delivery of the first real thinking chunk.

**Architecture:** Keep initialized MCP catalogs usable with stale-while-revalidate and generation-guarded atomic swaps, then schedule bounded recent-user warmup after API startup. Reduce the remaining pre-model path by adopting already-created traces and gathering independent model/backend/tool/checkpointer preparation, while safe milestone logging makes each remaining delay attributable.

**Tech Stack:** Python 3.12, asyncio, FastAPI lifespan, LangGraph/deepagents, MongoDB/Motor, Redis, pytest/pytest-asyncio, React 19, TypeScript, Vitest

## Global Constraints

- Work in `/home/yangyang/LambChat` on the current branch; do not create a worktree, push, or modify unrelated dirty files.
- Follow strict RED-GREEN-REFACTOR: each production behavior starts with a focused failing test and the expected failure must be observed.
- Explicit MCP configuration/policy/preference invalidation must beat every in-flight background refresh.
- Never log MCP URLs, headers, tool schemas/arguments, user messages, provider content, exception bodies, or secret-bearing dynamic metric names.
- Preserve Search Agent lazy sandbox behavior and existing tool authorization/quota semantics.
- Preserve actual provider streaming timing; do not add fabricated thinking content or lower thinking intensity.
- Use existing configuration fields where possible; do not touch the currently dirty `src/kernel/config/base.py` unless an unavoidable conflict is first reported.

---

### Task 1: Make expired MCP entries stale-while-revalidate

**Files:**
- Modify: `src/infra/tool/mcp_global.py`
- Modify: `tests/infra/tool/test_mcp_global_pubsub.py`

**Interfaces:**
- Consumes: existing `GlobalMCPEntry`, `_local_locks`, `_background_tasks`, `MCPClientManager.initialize()`, and cache invalidation Pub/Sub.
- Produces: `get_global_mcp_tools(user_id)` returning an initialized stale entry immediately; one generation-guarded refresh task per user; refresh tasks drained by `drain_background_tasks()`.

- [ ] **Step 1: Write the failing stale-return and single-flight tests**

Add gated manager fixtures and these behaviors to `tests/infra/tool/test_mcp_global_pubsub.py`:

```python
@pytest.mark.asyncio
async def test_expired_initialized_entry_returns_before_background_refresh_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refresh_started = asyncio.Event()
    release_refresh = asyncio.Event()
    old_manager = _FakeManager()
    old_tools = [object()]
    mcp_global._global_entries["user-1"] = mcp_global.GlobalMCPEntry(
        manager=old_manager,
        tools=old_tools,
        created_at=0,
    )

    class _RefreshingManager(_FakeManager):
        async def initialize(self) -> None:
            refresh_started.set()
            await release_refresh.wait()
            self._initialized = True

        async def get_tools(self) -> list[object]:
            return [object()]

    async def _acquired_lock(_lock_key: str, ttl: int = 30) -> tuple[bool, str]:
        assert ttl == mcp_global.DISTRIBUTED_LOCK_TTL
        return True, "test-lock"

    async def _released_lock(lock_key: str, lock_value: str) -> bool:
        assert lock_key == f"{mcp_global.LOCK_KEY_PREFIX}user-1"
        assert lock_value == "test-lock"
        return True

    async def _mark_done(user_id: str) -> None:
        assert user_id == "user-1"

    monkeypatch.setattr(mcp_global.settings, "MCP_GLOBAL_CACHE_TTL_SECONDS", 1)
    monkeypatch.setattr(mcp_global, "acquire_distributed_lock", _acquired_lock)
    monkeypatch.setattr(mcp_global, "release_distributed_lock", _released_lock)
    monkeypatch.setattr(mcp_global, "mark_init_done", _mark_done)
    monkeypatch.setitem(
        sys.modules,
        "src.infra.tool.mcp_client",
        SimpleNamespace(MCPClientManager=_RefreshingManager),
    )

    tools, manager = await asyncio.wait_for(
        mcp_global.get_global_mcp_tools("user-1"),
        timeout=0.1,
    )
    await asyncio.wait_for(refresh_started.wait(), timeout=1)

    assert tools is old_tools
    assert manager is old_manager
    assert len(mcp_global._refresh_tasks) == 1

    second_tools, second_manager = await mcp_global.get_global_mcp_tools("user-1")
    assert second_tools is old_tools
    assert second_manager is old_manager
    assert len(mcp_global._refresh_tasks) == 1

    release_refresh.set()
    await mcp_global.drain_background_tasks(timeout=1)
    assert mcp_global._global_entries["user-1"].manager is not old_manager
    assert old_manager.close_calls == 1
```

Also add tests named:

```python
test_refresh_failure_keeps_stale_entry_and_applies_retry_cooldown
test_invalidation_during_refresh_does_not_reinstall_invalidated_entry
test_invalidate_all_during_refresh_does_not_reinstall_any_entry
test_close_global_mcp_cache_drains_refresh_before_final_close
```

Update the autouse reset fixture to drain pending tasks and clear `_refresh_tasks`, `_user_generations`, `_refresh_retry_after`, and the global epoch between tests.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
uv run pytest tests/infra/tool/test_mcp_global_pubsub.py -k "expired_initialized or refresh_failure or invalidation_during_refresh or invalidate_all_during_refresh or drains_refresh" -vv
```

Expected: FAIL because expired entries enter the existing foreground initialization path and the refresh state/generation guards do not exist.

- [ ] **Step 3: Extract cold entry construction and implement background refresh**

In `src/infra/tool/mcp_global.py`, add process-local refresh state:

```python
MCP_REFRESH_RETRY_COOLDOWN_SECONDS = 30.0

_refresh_tasks: dict[str, asyncio.Task[None]] = {}
_user_generations: dict[str, int] = {}
_refresh_retry_after: dict[str, float] = {}
_cache_epoch = 0
```

Extract the manager construction portion of `get_global_mcp_tools()` into:

```python
async def _build_global_entry(user_id: str) -> GlobalMCPEntry:
    from src.infra.tool.mcp_client import MCPClientManager

    manager = MCPClientManager(config_path=None, user_id=user_id, use_database=True)
    try:
        await manager.initialize()
        tools = await manager.get_tools()
        return GlobalMCPEntry(manager=manager, tools=tools)
    except BaseException:
        await manager.close()
        raise
```

Keep the current distributed-lock acquisition/renew/release around calls to this helper. Do not install the entry inside `_build_global_entry()`.

Add the generation-guarded refresher:

```python
async def _refresh_global_entry(
    user_id: str,
    stale_entry: GlobalMCPEntry,
    epoch: int,
    generation: int,
) -> None:
    global _cache_epoch

    replacement: GlobalMCPEntry | None = None
    try:
        replacement = await _build_global_entry_with_distributed_lock(user_id)
        async with _get_local_lock(user_id):
            if (
                _cache_epoch != epoch
                or _user_generations.get(user_id, 0) != generation
                or _global_entries.get(user_id) is not stale_entry
            ):
                return
            _global_entries[user_id] = replacement
            replacement = None
            _refresh_retry_after.pop(user_id, None)
        _schedule_manager_close(stale_entry.manager)
    except Exception:
        async with _get_local_lock(user_id):
            if _global_entries.get(user_id) is stale_entry:
                _refresh_retry_after[user_id] = (
                    time.monotonic() + MCP_REFRESH_RETRY_COOLDOWN_SECONDS
                )
        logger.warning("mcp_cache_refresh_failed", extra={"cache_status": "refresh"})
    finally:
        if replacement is not None:
            await replacement.manager.close()
```

Add `_schedule_entry_refresh()` that checks the retry deadline, uses one task per user, stores it in `_refresh_tasks`, tracks it in `_background_tasks`, and removes only the identical completed task from `_refresh_tasks`.

Change both fast-path checks in `get_global_mcp_tools()` so any initialized entry is returned. Fresh entries log `cache_status=fresh`; expired entries log `cache_status=stale` and schedule refresh before returning. Remove `_cleanup_expired_entries()` from periodic request cleanup; LRU capacity remains the eviction boundary.

Increment `_user_generations[user_id]` before user invalidation removes an entry. Increment `_cache_epoch` before all-cache invalidation. A late replacement must be closed rather than installed.

- [ ] **Step 4: Run the focused MCP tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/tool/test_mcp_global_pubsub.py -vv
```

Expected: all tests pass; the gated stale request returns before `release_refresh` is set.

- [ ] **Step 5: Refactor duplicated cold/refresh lock handling**

Keep one helper for distributed lock lifecycle and one helper for manager construction. Preserve the existing lock renewal, wait limit, `mark_init_done`, LRU cleanup, and failure isolation. Re-run the full file after refactoring.

- [ ] **Step 6: Commit Task 1**

```bash
git add src/infra/tool/mcp_global.py tests/infra/tool/test_mcp_global_pubsub.py
git commit -m "perf: refresh stale MCP catalogs in background"
```

---

### Task 2: Warm recent MCP users without blocking startup

**Files:**
- Modify: `src/infra/tool/mcp_global.py`
- Modify: `src/api/main.py`
- Modify: `tests/infra/tool/test_mcp_global_pubsub.py`
- Modify: `tests/api/test_startup_warmups.py`

**Interfaces:**
- Consumes: `warmup_global_cache(user_ids)`, trace documents with `user_id` and `started_at`, FastAPI lifespan task ownership.
- Produces: `warmup_active_users_mcp(limit)` selecting most recently active unique users; `_schedule_mcp_cache_warmup(app)` storing `app.state.mcp_cache_warmup_task` without delaying readiness.

- [ ] **Step 1: Write failing recent-user and non-blocking scheduler tests**

Replace the arbitrary-users fake in the warmup test with a trace aggregate contract:

```python
@pytest.mark.asyncio
async def test_warmup_active_users_selects_recent_unique_trace_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warmed: list[str] = []
    captured_pipeline: list[dict] = []

    class _FakeCursor:
        def __aiter__(self):
            self._iterator = iter([{"_id": "recent-user"}, {"_id": "older-user"}])
            return self

        async def __anext__(self):
            try:
                return next(self._iterator)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class _FakeCollection:
        def aggregate(self, pipeline):
            captured_pipeline.extend(pipeline)
            return _FakeCursor()

    class _FakeClient:
        def __getitem__(self, _name):
            return {"traces": _FakeCollection()}

    async def _warm(user_ids: list[str]) -> None:
        warmed.extend(user_ids)

    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: _FakeClient())
    monkeypatch.setattr(mcp_global, "warmup_global_cache", _warm)

    await mcp_global.warmup_active_users_mcp(limit=2)

    assert warmed == ["recent-user", "older-user"]
    assert {"$sort": {"started_at": -1}} in captured_pipeline
    assert {"$limit": 2} in captured_pipeline
```

Add to `tests/api/test_startup_warmups.py`:

```python
@pytest.mark.asyncio
async def test_schedule_mcp_cache_warmup_does_not_delay_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow_warmup(limit: int = 0) -> None:
        assert limit == 0
        started.set()
        await release.wait()

    monkeypatch.setattr(
        "src.infra.tool.mcp_global.warmup_active_users_mcp",
        _slow_warmup,
    )
    app = SimpleNamespace(state=SimpleNamespace())

    task = api_main._schedule_mcp_cache_warmup(app)
    await asyncio.wait_for(started.wait(), timeout=1)

    assert task is app.state.mcp_cache_warmup_task
    assert task.done() is False
    release.set()
    await task
```

- [ ] **Step 2: Run the two tests and verify RED**

Run:

```bash
uv run pytest tests/infra/tool/test_mcp_global_pubsub.py::test_warmup_active_users_selects_recent_unique_trace_users tests/api/test_startup_warmups.py::test_schedule_mcp_cache_warmup_does_not_delay_startup -vv
```

Expected: FAIL because warmup reads `users` rather than recent traces and no API scheduler exists.

- [ ] **Step 3: Implement recent-trace selection and lifespan scheduling**

Use this bounded aggregation in `warmup_active_users_mcp()`:

```python
pipeline: list[dict[str, Any]] = [
    {"$match": {"user_id": {"$type": "string", "$ne": ""}}},
    {"$sort": {"started_at": -1}},
    {"$group": {"_id": "$user_id", "last_active": {"$first": "$started_at"}}},
    {"$sort": {"last_active": -1}},
    {"$limit": effective_limit},
]
cursor = db[settings.MONGODB_TRACES_COLLECTION].aggregate(pipeline)
```

Add scheduler helpers beside `_schedule_models_cache_warmup()` in `src/api/main.py`:

```python
async def _warm_mcp_cache() -> None:
    try:
        from src.infra.tool.mcp_global import warmup_active_users_mcp

        await warmup_active_users_mcp(limit=0)
    except Exception:
        logger.warning("MCP cache warm-up failed", exc_info=True)


def _schedule_mcp_cache_warmup(app: FastAPI) -> asyncio.Task[None]:
    task = asyncio.create_task(_warm_mcp_cache(), name="mcp-cache-warmup")
    app.state.mcp_cache_warmup_task = task
    return task
```

Schedule it after `start_runtime_services()` and include the task in the existing lifespan shutdown cancellation/drain path. Do not await it during startup.

- [ ] **Step 4: Run warmup tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/tool/test_mcp_global_pubsub.py -k warmup -vv
uv run pytest tests/api/test_startup_warmups.py -vv
```

Expected: all selected tests pass.

- [ ] **Step 5: Commit Task 2**

```bash
git add src/infra/tool/mcp_global.py src/api/main.py tests/infra/tool/test_mcp_global_pubsub.py tests/api/test_startup_warmups.py
git commit -m "perf: warm recent MCP users after startup"
```

---

### Task 3: Remove duplicate trace creation and overlap task preflight

**Files:**
- Modify: `src/infra/task/executor.py`
- Create: `tests/infra/task/test_executor_startup_latency.py`

**Interfaces:**
- Consumes: `run_task(..., existing_trace_id, user_message_written)`, `Presenter._trace_created`, `TaskHeartbeat.start()`, and `_update_session_status()`.
- Produces: pre-created trace adoption only when both proof fields are present; concurrent heartbeat and `RUNNING` transition completed before the agent executor begins.

- [ ] **Step 1: Write failing behavior tests with real `TaskExecutor.run_task()`**

Create `tests/infra/task/test_executor_startup_latency.py` with complete fakes for storage, heartbeat, Presenter, dual writer, notification, and terminal stream expiry. Add:

```python
@pytest.mark.asyncio
async def test_precreated_user_message_trace_skips_duplicate_trace_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_presenter = _FakePresenter(trace_id="trace-1")
    executor = _executor(monkeypatch, fake_presenter)

    await executor.run_task(
        session_id="session-1",
        run_id="run-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor=_empty_agent_stream,
        existing_trace_id="trace-1",
        user_message_written=True,
    )

    assert fake_presenter.ensure_trace_calls == 0
    assert fake_presenter.emitted_user_messages == []
```

```python
@pytest.mark.asyncio
async def test_heartbeat_and_running_status_overlap_before_agent_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heartbeat_started = asyncio.Event()
    running_started = asyncio.Event()
    release = asyncio.Event()
    agent_started = asyncio.Event()
    executor = _gated_executor(
        monkeypatch,
        heartbeat_started=heartbeat_started,
        running_started=running_started,
        release=release,
    )

    async def _agent_stream(*_args, **_kwargs):
        agent_started.set()
        if False:
            yield {}

    task = asyncio.create_task(
        executor.run_task(
            "session-1",
            "run-1",
            "search",
            "hello",
            "user-1",
            _agent_stream,
            existing_trace_id="trace-1",
            user_message_written=True,
        )
    )

    await asyncio.wait_for(heartbeat_started.wait(), timeout=1)
    await asyncio.wait_for(running_started.wait(), timeout=1)
    assert agent_started.is_set() is False

    release.set()
    await task
    assert agent_started.is_set() is True
```

Add the inverse test `test_unproven_existing_trace_still_calls_ensure_trace` with `user_message_written=False`.

- [ ] **Step 2: Run the new test file and verify RED**

Run:

```bash
uv run pytest tests/infra/task/test_executor_startup_latency.py -vv
```

Expected: duplicate `_ensure_trace()` is observed and heartbeat completes before the `RUNNING` update starts.

- [ ] **Step 3: Reorder proven-trace detection and gather independent preflight work**

In `run_task()`, compute proof before `_ensure_trace()`:

```python
already_written = user_message_written or self._run_info.get(run_id, {}).get(
    "user_message_written",
    False,
)
trace_precreated = bool(existing_trace_id and already_written)
```

After constructing Presenter:

```python
if trace_precreated:
    presenter._trace_created = True
else:
    await presenter._ensure_trace()
```

Keep the initial `STARTING` transition first. Then overlap only the independent operations:

```python
await asyncio.gather(
    self._heartbeat.start(run_id, user_id=user_id),
    self._update_session_status(session_id, TaskStatus.RUNNING, run_id=run_id),
)
```

Do not advance the agent async generator until both complete. Preserve the existing `finally` heartbeat stop and every terminal status path.

- [ ] **Step 4: Run task tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/task/test_executor_startup_latency.py tests/infra/task/test_executor_notifications.py tests/infra/task/test_cancellation_token_usage.py -vv
```

Expected: all selected tests pass with existing cancellation/notification ordering intact.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/infra/task/executor.py tests/infra/task/test_executor_startup_latency.py
git commit -m "perf: overlap chat task preflight"
```

---

### Task 4: Gather independent Agent dependencies and MCP filters

**Files:**
- Create: `src/agents/core/startup_preparation.py`
- Create: `tests/agents/core/test_startup_preparation.py`
- Modify: `src/agents/core/tool_filter.py`
- Create: `tests/agents/core/test_tool_filter.py`
- Modify: `src/agents/search_agent/nodes.py`
- Modify: `src/agents/fast_agent/nodes.py`
- Modify: `src/agents/team_agent/nodes.py`
- Modify: `tests/agents/test_disabled_skills_config_propagation.py`
- Modify: `tests/agents/test_team_agent_sandbox_support.py`

**Interfaces:**
- Consumes: awaitables for model, backend bundle, skills prompt, context tools, and checkpointer.
- Produces: `PreparedAgentInputs` with the same resolved values as the current sequential code; `get_db_disabled_mcp_tool_names()` returning the same union from concurrent queries.

- [ ] **Step 1: Write the failing core concurrency test**

Create `tests/agents/core/test_startup_preparation.py`:

```python
@pytest.mark.asyncio
async def test_prepare_agent_inputs_starts_all_independent_work_together() -> None:
    release = asyncio.Event()
    started: set[str] = set()

    async def gated(name: str, value):
        started.add(name)
        await release.wait()
        return value

    task = asyncio.create_task(
        prepare_agent_inputs(
            model=gated("model", "llm"),
            backend=gated("backend", "backend"),
            skills_prompt=gated("skills", "skills"),
            tools=gated("tools", ["tool"]),
            checkpointer=gated("checkpointer", "checkpointer"),
        )
    )

    for _ in range(20):
        if len(started) == 5:
            break
        await asyncio.sleep(0)

    assert started == {"model", "backend", "skills", "tools", "checkpointer"}
    assert task.done() is False

    release.set()
    result = await task
    assert result == PreparedAgentInputs(
        model="llm",
        backend="backend",
        skills_prompt="skills",
        tools=["tool"],
        checkpointer="checkpointer",
    )
```

Add `test_prepare_agent_inputs_cancels_siblings_when_one_dependency_fails` so a failed preparation cannot leave background coroutines mutating request context after the node exits.

- [ ] **Step 2: Write the failing MCP filter concurrency test**

Create `tests/agents/core/test_tool_filter.py` with three gated storage methods. Start `get_db_disabled_mcp_tool_names("user-1")`, assert all three methods start before release, then release and assert the literal union:

```python
assert result == {
    "system-server:blocked-system-tool",
    "user-server:blocked-user-tool",
    "preference-server:blocked-preference-tool",
}
```

- [ ] **Step 3: Run the new core tests and verify RED**

Run:

```bash
uv run pytest tests/agents/core/test_startup_preparation.py tests/agents/core/test_tool_filter.py -vv
```

Expected: import failure for the new preparation module and the sequential storage queries cannot all reach their gates.

- [ ] **Step 4: Implement the preparation primitive and concurrent filter queries**

Create `src/agents/core/startup_preparation.py`:

```python
from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreparedAgentInputs:
    model: Any
    backend: Any
    skills_prompt: str
    tools: list[Any]
    checkpointer: Any


async def prepare_agent_inputs(
    *,
    model: Awaitable[Any],
    backend: Awaitable[Any],
    skills_prompt: Awaitable[str],
    tools: Awaitable[list[Any]],
    checkpointer: Awaitable[Any],
) -> PreparedAgentInputs:
    async with asyncio.TaskGroup() as group:
        model_task = group.create_task(model)
        backend_task = group.create_task(backend)
        skills_task = group.create_task(skills_prompt)
        tools_task = group.create_task(tools)
        checkpointer_task = group.create_task(checkpointer)
    return PreparedAgentInputs(
        model=model_task.result(),
        backend=backend_task.result(),
        skills_prompt=skills_task.result(),
        tools=tools_task.result(),
        checkpointer=checkpointer_task.result(),
    )
```

In `get_db_disabled_mcp_tool_names()`, replace the three sequential awaits with:

```python
system_disabled, user_server_disabled, user_tool_disabled = await asyncio.gather(
    storage.get_system_disabled_tools(),
    storage.get_user_server_disabled_tools(user_id),
    storage.get_disabled_tool_names(user_id),
)
```

Keep the current outer exception handler and literal union logic.

- [ ] **Step 5: Migrate Search, Fast, and Team node preparation**

For each node, create small local async loaders that return the current values without changing their semantics:

```python
async def _load_context_tools() -> list[Any]:
    get_tools = getattr(context, "get_tools", None)
    if callable(get_tools):
        maybe_tools = get_tools()
        if inspect.isawaitable(maybe_tools):
            await maybe_tools
    filter_tools = getattr(context, "filter_tools", None)
    return list(filter_tools() if callable(filter_tools) else getattr(context, "tools", []))


async def _load_skills_prompt() -> str:
    if not settings.ENABLE_SKILLS or not context.skills:
        return ""
    return await build_skills_prompt(context.skills)
```

Search passes `_create_backend_and_prompt(...)` as the backend awaitable. Fast and Team wrap their existing store/backend construction in one async loader returning the existing tuple. All three pass `LLMClient.get_model(...)`, `get_async_checkpointer(thread_id=...)`, and the two loaders to `prepare_agent_inputs()`.

After the gather, unpack values into the same local names used today, then execute deferred-tool insertion, middleware creation, graph compilation, and streaming unchanged. Keep Search's lazy sandbox and every current fail-open warning by catching inside the relevant loader where the sequential code currently catches.

Extend the existing node fixtures with gated loaders and add one Search, one Fast, and one Team test proving all five dependencies start before release and the resulting graph receives the literal backend/tool/checkpointer objects.

- [ ] **Step 6: Run focused Agent tests and verify GREEN**

Run:

```bash
uv run pytest tests/agents/core/test_startup_preparation.py tests/agents/core/test_tool_filter.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py -vv
```

Expected: all tests pass and existing prompt/tool/backend propagation assertions remain unchanged.

- [ ] **Step 7: Commit Task 4**

```bash
git add src/agents/core/startup_preparation.py tests/agents/core/test_startup_preparation.py src/agents/core/tool_filter.py tests/agents/core/test_tool_filter.py src/agents/search_agent/nodes.py src/agents/fast_agent/nodes.py src/agents/team_agent/nodes.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py
git commit -m "perf: prepare chat agent dependencies concurrently"
```

---

### Task 5: Add safe first-event phase evidence and lock in thinking delivery

**Files:**
- Create: `src/infra/agent/first_event_timing.py`
- Create: `tests/infra/agent/test_first_event_timing.py`
- Modify: `src/infra/agent/events/processor.py`
- Modify: `src/infra/agent/events/stream.py`
- Modify: `tests/infra/agent/test_events_processor.py`
- Modify: `frontend/src/hooks/useAgent/__tests__/eventProcessor.test.ts`

**Interfaces:**
- Consumes: monotonic clock, top-level `on_chat_model_start` and `on_chat_model_stream` events, existing Presenter thinking events.
- Produces: one safe structured log per first provider milestone; no stream payload changes.

- [ ] **Step 1: Write failing timing tests**

Create `tests/infra/agent/test_first_event_timing.py`:

```python
def test_first_event_timing_records_each_allowlisted_phase_once(caplog) -> None:
    times = iter([10.0, 10.4, 10.7, 11.2])
    timing = FirstEventTiming(clock=lambda: next(times))

    with caplog.at_level(logging.INFO, logger="src.infra.agent.first_event_timing"):
        timing.start_model()
        timing.record_once("provider_first_delta")
        timing.record_once("provider_first_reasoning")
        timing.record_once("provider_first_reasoning")

    phases = [record.first_event_phase for record in caplog.records]
    assert phases == ["provider_first_delta", "provider_first_reasoning"]
    assert [record.duration_ms for record in caplog.records] == [400.0, 700.0]
```

```python
def test_first_event_timing_rejects_dynamic_phase_names() -> None:
    timing = FirstEventTiming(clock=lambda: 0.0)
    with pytest.raises(ValueError, match="Unsupported first-event phase"):
        timing.record_once("session-secret")  # type: ignore[arg-type]
```

Extend processor tests with a top-level model-start followed by an empty delta,
one reasoning delta, and one text delta. Assert timing receives exactly:

```python
["provider_first_delta", "provider_first_reasoning", "provider_first_text"]
```

and Presenter emission remains `thinking` before `message:chunk`.

- [ ] **Step 2: Run timing/processor tests and verify RED**

Run:

```bash
uv run pytest tests/infra/agent/test_first_event_timing.py tests/infra/agent/test_events_processor.py -k "first_event or reasoning_content or thinking" -vv
```

Expected: import failure for `FirstEventTiming` and no processor milestone calls.

- [ ] **Step 3: Implement allowlisted milestone timing**

Create `src/infra/agent/first_event_timing.py` with:

```python
from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from src.infra.logging import get_logger

logger = get_logger(__name__)
FirstEventPhase = Literal[
    "provider_first_delta",
    "provider_first_reasoning",
    "provider_first_text",
]
_ALLOWED_PHASES = frozenset(
    {"provider_first_delta", "provider_first_reasoning", "provider_first_text"}
)


class FirstEventTiming:
    def __init__(self, clock: Callable[[], float] = time.perf_counter) -> None:
        self._clock = clock
        self._model_started_at: float | None = None
        self._seen: set[str] = set()

    def start_model(self) -> None:
        if self._model_started_at is None:
            self._model_started_at = self._clock()

    def record_once(self, phase: FirstEventPhase) -> None:
        if phase not in _ALLOWED_PHASES:
            raise ValueError(f"Unsupported first-event phase: {phase}")
        if phase in self._seen or self._model_started_at is None:
            return
        self._seen.add(phase)
        logger.info(
            "first_event_timing",
            extra={
                "first_event_phase": phase,
                "duration_ms": round((self._clock() - self._model_started_at) * 1000, 2),
            },
        )
```

Give `AgentEventProcessor` one timing instance, include top-level `on_chat_model_start` in routing, and record milestones before buffering:

- every first top-level stream chunk: `provider_first_delta`;
- first non-empty reasoning block/string: `provider_first_reasoning`;
- first non-empty text block/string: `provider_first_text`.

Do not pass content or provider exceptions into the timing helper.

- [ ] **Step 4: Add frontend existing-contract coverage**

Add this pure behavior test to `frontend/src/hooks/useAgent/__tests__/eventProcessor.test.ts`:

```typescript
test("one thinking event immediately creates a streaming thinking part", () => {
  const result = processMessageEvent(
    "thinking",
    { content: "first", thinking_id: "thinking-1" },
    [],
    "",
    [],
    0,
    [],
    true,
    "message-1",
  );

  expect(result.parts).toEqual([
    {
      type: "thinking",
      content: "first",
      thinking_id: "thinking-1",
      isStreaming: true,
      depth: 0,
      agent_id: undefined,
    },
  ]);
});
```

This is characterization coverage for the already-correct frontend path; it does not authorize a production TypeScript change.

- [ ] **Step 5: Run backend and frontend tests and verify GREEN**

Run:

```bash
uv run pytest tests/infra/agent/test_first_event_timing.py tests/infra/agent/test_events_processor.py -vv
cd frontend && pnpm test -- src/hooks/useAgent/__tests__/eventProcessor.test.ts
```

Expected: all tests pass; the first reasoning Presenter event remains immediate.

- [ ] **Step 6: Commit Task 5**

```bash
git add src/infra/agent/first_event_timing.py tests/infra/agent/test_first_event_timing.py src/infra/agent/events/processor.py src/infra/agent/events/stream.py tests/infra/agent/test_events_processor.py frontend/src/hooks/useAgent/__tests__/eventProcessor.test.ts
git commit -m "perf: expose safe first-event phase timing"
```

---

### Task 6: Focused verification and runtime timing comparison

**Files:**
- Modify only if verification reveals a defect in the files already listed above.

**Interfaces:**
- Consumes: all changed modules and the approved target session timing method.
- Produces: focused test/lint/type evidence and a cold/warm/stale runtime comparison without exposing content.

- [ ] **Step 1: Run the focused backend suite**

```bash
uv run pytest tests/infra/tool/test_mcp_global_pubsub.py tests/api/test_startup_warmups.py tests/infra/task/test_executor_startup_latency.py tests/infra/task/test_executor_notifications.py tests/agents/core/test_startup_preparation.py tests/agents/core/test_tool_filter.py tests/agents/test_disabled_skills_config_propagation.py tests/agents/test_team_agent_sandbox_support.py tests/infra/agent/test_first_event_timing.py tests/infra/agent/test_events_processor.py -vv
```

Expected: all selected tests pass.

- [ ] **Step 2: Run focused frontend verification**

```bash
cd frontend && pnpm test -- src/hooks/useAgent/__tests__/eventProcessor.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run static checks on changed code**

```bash
uv run ruff check src/infra/tool/mcp_global.py src/api/main.py src/infra/task/executor.py src/agents/core/startup_preparation.py src/agents/core/tool_filter.py src/agents/search_agent/nodes.py src/agents/fast_agent/nodes.py src/agents/team_agent/nodes.py src/infra/agent/first_event_timing.py src/infra/agent/events/processor.py src/infra/agent/events/stream.py tests/infra/tool/test_mcp_global_pubsub.py tests/api/test_startup_warmups.py tests/infra/task/test_executor_startup_latency.py tests/agents/core/test_startup_preparation.py tests/agents/core/test_tool_filter.py tests/infra/agent/test_first_event_timing.py
uv run mypy src/infra/tool/mcp_global.py src/api/main.py src/infra/task/executor.py src/agents/core/startup_preparation.py src/agents/core/tool_filter.py src/agents/search_agent/nodes.py src/agents/fast_agent/nodes.py src/agents/team_agent/nodes.py src/infra/agent/first_event_timing.py src/infra/agent/events/processor.py src/infra/agent/events/stream.py
git diff --check
```

Expected: all commands exit 0. If repository-wide existing failures appear outside the touched paths, isolate and report them rather than changing unrelated code.

- [ ] **Step 4: Restart the local runtime and measure three safe timelines**

After preserving the user's current launch method, restart only if needed to load the completed backend code. Measure, without printing content:

1. first turn after startup warmup;
2. immediately following warm turn;
3. an expired-entry unit/integration scenario proving stale return before gated refresh.

For real session traces, report only event types, timestamps, content lengths, cache status, and durations. Confirm:

- no expired-cache foreground discovery gap;
- provider reasoning timestamp to Presenter thinking timestamp remains within milliseconds;
- warm first-thinking is materially below the prior 4.40-5.67 second baseline under comparable provider timing.

- [ ] **Step 5: Run verification-before-completion and inspect final scope**

Invoke `superpowers:verification-before-completion`, run its required fresh checks, then inspect:

```bash
git status --short
git log --oneline -8
git diff --stat HEAD~5..HEAD
```

Confirm unrelated dirty files remain untouched and every task commit contains only its declared files.
