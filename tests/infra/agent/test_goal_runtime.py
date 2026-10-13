from types import SimpleNamespace

import pytest

from src.infra.goal_runtime import GoalRunMetrics, bind_submission_goal
from src.infra.persistent_goal import GoalService
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.persistent_goal import PersistentGoalCreate
from tests.infra.agent.test_persistent_goal import Store


@pytest.fixture(autouse=True)
def runtime_redis(monkeypatch):
    class Redis:
        def __init__(self):
            self.values = {}
            self.expirations = {}
            self.renew_error = False

        async def set(self, key, token, *, nx, ex):
            if nx and key in self.values:
                return False
            self.values[key] = token
            self.expirations[key] = ex
            return True

        async def eval(self, script, count, key, token, *args):
            if "expire" in script and self.renew_error:
                raise ConnectionError("lease backend unavailable")
            if self.values.get(key) != token:
                return 0
            if "expire" in script:
                self.expirations[key] = args[0]
            else:
                del self.values[key]
            return 1

    redis = Redis()
    monkeypatch.setattr("src.infra.channel.chat_lease.get_redis_client", lambda: redis)
    monkeypatch.setattr("src.infra.goal_runtime.GOAL_LEASE_RENEW_SECONDS", 0.01, raising=False)
    return redis


def test_usage_snapshot_not_summed_and_missing_usage_stays_unknown():
    metrics = GoalRunMetrics()
    assert metrics.tokens is None
    metrics.observe({"event": "token:usage", "data": {"total_tokens": 10}})
    metrics.observe({"event": "token:usage", "data": {"total_tokens": 20}})
    assert metrics.tokens == 20
    metrics.observe({"event": "tool:result", "data": {"id": "t"}})
    metrics.observe({"event": "tool:result", "data": {"id": "t"}})
    assert metrics.tool_count == 1


async def test_ordinary_goal_never_queries_persistent_store():
    request = AgentRequest(message="hello")
    service = SimpleNamespace(get=lambda *args: (_ for _ in ()).throw(AssertionError("no opt-in")))
    value, run_id = await bind_submission_goal(request, {}, "s", "u", "r", service=service)
    assert value is None
    assert run_id == "r"


async def test_user_turn_supersedes_automatic_intent_and_gets_authoritative_scope():
    service = GoalService(Store())
    goal = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    old = await service.reserve("s", "u", goal.version)
    request = AgentRequest(message="also verify logs")
    active, run_id = await bind_submission_goal(
        request, {"persistent_goal_id": goal.id}, "s", "u", "human", service=service
    )
    assert run_id == "human"
    assert active["_persistent_version"] > old.version
    assert active["_persistent_id"] == goal.id
    assert request.goal.objective == "finish"
    assert (await service.get("s", "u")).current_run_id == "human"


async def test_budget_callback_counts_nested_models_once_and_carries_unknown_usage():
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult

    from src.infra.goal_runtime import GoalUsageCallback

    metrics = GoalRunMetrics()
    callback = GoalUsageCallback(metrics)
    response = LLMResult(
        generations=[
            [
                ChatGeneration(
                    message=AIMessage(
                        content="ok",
                        usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
                    )
                )
            ]
        ]
    )
    await callback.on_llm_end(response, run_id="model-1")
    await callback.on_llm_end(response, run_id="model-1")
    await callback.on_llm_end(response, run_id="child-1")
    assert metrics.tokens == 10


async def test_actual_agent_tool_execution_stops_at_model_budget_boundary():
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool

    from src.infra.goal_runtime import GoalUsageCallback
    from src.infra.task.exceptions import TaskInterruptedError

    class ToolModel(FakeMessagesListChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    called = []

    @tool
    def write_result() -> str:
        """Write the final result."""
        called.append(True)
        return "written"

    model = ToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "write_result", "args": {}, "id": "t"}],
                usage_metadata={"input_tokens": 7, "output_tokens": 3, "total_tokens": 10},
            )
        ]
    )
    metrics = GoalRunMetrics()

    async def enforce():
        if metrics.tokens is not None and metrics.tokens >= 5:
            raise TaskInterruptedError("budget reached")

    metrics.enforce = enforce
    agent = create_agent(model, tools=[write_result])
    with pytest.raises(TaskInterruptedError, match="budget"):
        await agent.ainvoke(
            {"messages": [{"role": "user", "content": "write result"}]},
            {"callbacks": [GoalUsageCallback(metrics)]},
        )
    assert not called


async def test_tool_boundary_checks_live_authority_before_side_effect():
    from src.infra.goal_runtime import GoalUsageCallback
    from src.infra.task.exceptions import TaskInterruptedError

    metrics = GoalRunMetrics()

    async def enforce():
        raise TaskInterruptedError("superseded")

    metrics.enforce = enforce
    with pytest.raises(TaskInterruptedError, match="superseded"):
        await GoalUsageCallback(metrics).on_tool_start({}, "{}", run_id="t")


async def test_no_event_host_await_is_stopped_when_goal_is_superseded(monkeypatch):
    import asyncio

    from src.infra.goal_runtime import guarded_goal_stream
    from src.infra.task.exceptions import TaskInterruptedError

    service = GoalService(Store())
    goal = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    reserved = await service.reserve("s", "u", goal.version)
    entered, closed = asyncio.Event(), asyncio.Event()
    monkeypatch.setattr("src.infra.goal_runtime.GoalService", lambda: service)
    presenter = SimpleNamespace(run_id=reserved.current_run_id)

    async def source():
        try:
            entered.set()
            await asyncio.Event().wait()
            yield {"event": "done"}
        finally:
            closed.set()

    async def consume():
        async for event in guarded_goal_stream(
            source(),
            active_goal={"_persistent_id": goal.id, "_persistent_version": goal.version},
            session_id="s",
            user_id="u",
            presenter=presenter,
        ):
            pass

    task = asyncio.create_task(consume())
    await entered.wait()
    await service.control("s", "u", "pause")
    with pytest.raises(TaskInterruptedError):
        await asyncio.wait_for(task, 2)
    assert closed.is_set()


async def test_rejected_submission_releases_only_its_own_goal_reservation(monkeypatch):
    from src.infra.goal_runtime import SUBMISSION_GOAL, rollback_submission_goal

    service = GoalService(Store())
    goal = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    request = AgentRequest(message="continue")
    token = SUBMISSION_GOAL.set(None)
    try:
        await bind_submission_goal(
            request, {"persistent_goal_id": goal.id}, "s", "u", "rejected", service=service
        )
        await rollback_submission_goal(service=service)
        assert (await service.get("s", "u")).current_run_id is None
        assert not (await service.get("s", "u")).intent_submitted
    finally:
        SUBMISSION_GOAL.reset(token)


async def _runtime_goal(monkeypatch):
    service = GoalService(Store())
    goal = await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    run = await service.reserve("s", "u", goal.version)
    monkeypatch.setattr("src.infra.goal_runtime.GoalService", lambda: service)

    async def ignore(*args, **kwargs):
        pass

    monkeypatch.setattr("src.infra.goal_runtime.publish_goal", ignore)
    return service, {
        "active_goal": {"_persistent_id": goal.id, "_persistent_version": run.version},
        "session_id": "s",
        "user_id": "u",
        "presenter": SimpleNamespace(run_id=run.current_run_id),
    }


class SilentSource:
    def __init__(self):
        import asyncio

        self.entered = asyncio.Event()
        self.closing = asyncio.Event()
        self.closed = asyncio.Event()
        self.allow_close = asyncio.Event()
        self.allow_close.set()

    def __aiter__(self):
        return self

    async def __anext__(self):
        import asyncio

        self.entered.set()
        await asyncio.Event().wait()

    async def aclose(self):
        self.closing.set()
        await self.allow_close.wait()
        self.closed.set()


async def _consume_runtime(source, kwargs):
    from src.infra.goal_runtime import guarded_goal_stream

    async for _ in guarded_goal_stream(source, **kwargs):
        pass


async def test_duplicate_goal_runner_never_enters_source(monkeypatch, runtime_redis):
    import asyncio

    from src.infra.task.exceptions import TaskInterruptedError

    _, kwargs = await _runtime_goal(monkeypatch)
    first, duplicate = SilentSource(), SilentSource()
    task = asyncio.create_task(_consume_runtime(first, kwargs))
    await asyncio.wait_for(first.entered.wait(), 1)
    try:
        with pytest.raises(TaskInterruptedError, match="lease"):
            await asyncio.wait_for(_consume_runtime(duplicate, kwargs), 0.2)
        assert not duplicate.entered.is_set()
        assert duplicate.closed.is_set()
        assert set(runtime_redis.expirations.values()) == {60}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("backend_error", [False, True])
async def test_lease_loss_stops_silent_host_and_preserves_new_owner(
    monkeypatch, runtime_redis, backend_error
):
    import asyncio

    from src.infra.task.exceptions import TaskInterruptedError

    _, kwargs = await _runtime_goal(monkeypatch)
    source = SilentSource()
    task = asyncio.create_task(_consume_runtime(source, kwargs))
    await asyncio.wait_for(source.entered.wait(), 1)
    try:
        assert len(runtime_redis.values) == 1
        key = next(iter(runtime_redis.values))
        assert kwargs["active_goal"]["_persistent_id"] in key
        assert kwargs["presenter"].run_id in key
        if backend_error:
            runtime_redis.renew_error = True
        else:
            runtime_redis.values[key] = "new-owner"
        with pytest.raises(TaskInterruptedError, match="lease"):
            await asyncio.wait_for(task, 1)
        assert source.closed.is_set()
        if not backend_error:
            assert runtime_redis.values[key] == "new-owner"
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_execution_lease_is_held_until_source_cleanup_finishes(monkeypatch, runtime_redis):
    import asyncio

    _, kwargs = await _runtime_goal(monkeypatch)
    source = SilentSource()
    source.allow_close.clear()
    task = asyncio.create_task(_consume_runtime(source, kwargs))
    await asyncio.wait_for(source.entered.wait(), 1)
    task.cancel()
    try:
        await asyncio.wait_for(source.closing.wait(), 1)
        assert len(runtime_redis.values) == 1
        source.allow_close.set()
        await asyncio.gather(task, return_exceptions=True)
        assert source.closed.is_set()
        assert not runtime_redis.values
    finally:
        source.allow_close.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_authority_watchdog_error_stops_silent_execution(monkeypatch):
    import asyncio

    from src.infra.task.exceptions import TaskInterruptedError

    service, kwargs = await _runtime_goal(monkeypatch)
    source = SilentSource()
    task = asyncio.create_task(_consume_runtime(source, kwargs))
    await asyncio.wait_for(source.entered.wait(), 1)

    async def unavailable(*args):
        raise ConnectionError("authority unavailable")

    monkeypatch.setattr(service, "get", unavailable)
    try:
        with pytest.raises(TaskInterruptedError, match="authority"):
            await asyncio.wait_for(task, 1)
        assert source.closed.is_set()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("resume_payload", [None, {"approval_id": "approved"}])
async def test_waiting_goal_requires_approval_and_successful_resume_cas(
    monkeypatch, runtime_redis, resume_payload
):
    import asyncio

    from src.infra.task.exceptions import TaskInterruptedError

    service, kwargs = await _runtime_goal(monkeypatch)
    await service.control("s", "u", "waiting_human")
    if resume_payload:

        async def conflict(value):
            assert len(runtime_redis.values) == 1
            return None

        monkeypatch.setattr(service, "_save", conflict)
    source = SilentSource()
    with pytest.raises(TaskInterruptedError):
        await asyncio.wait_for(
            _consume_runtime(source, {**kwargs, "hitl_resume": resume_payload}), 0.2
        )
    assert not source.entered.is_set()
    assert source.closed.is_set()
    assert (await service.get("s", "u")).status == "waiting_human"
    assert not runtime_redis.values


async def test_approved_goal_resume_enters_source_with_execution_lease(monkeypatch, runtime_redis):
    import asyncio

    service, kwargs = await _runtime_goal(monkeypatch)
    await service.control("s", "u", "waiting_human")
    source = SilentSource()
    task = asyncio.create_task(
        _consume_runtime(source, {**kwargs, "hitl_resume": {"approval_id": "approved"}})
    )
    try:
        await asyncio.wait_for(source.entered.wait(), 1)
        assert (await service.get("s", "u")).status == "active"
        assert len(runtime_redis.values) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_task_executor_duplicate_lease_has_no_shared_lifecycle_effects(
    monkeypatch, runtime_redis
):
    from unittest.mock import AsyncMock

    from src.infra.channel.chat_lease import ChatLease
    from src.infra.task.cancellation import TaskCancellation
    from src.infra.task.exceptions import TaskInterruptedError
    from tests.infra.task.test_executor_startup_latency import _executor, _FakePresenter

    task_executor = _executor(monkeypatch)
    update = AsyncMock()
    clear = AsyncMock()
    monkeypatch.setattr(task_executor, "_update_session_status", update)
    monkeypatch.setattr(TaskCancellation, "clear_interrupt", clear)
    held = ChatLease("goal:runner:g:r", ttl=60)
    assert await held.acquire()
    called = []

    async def source(*args, **kwargs):
        called.append(True)
        yield {"event": "message:chunk", "data": {"content": "must not run"}}

    with pytest.raises(TaskInterruptedError, match="lease"):
        await task_executor.run_task(
            "s",
            "r",
            "fast",
            "continue",
            "u",
            source,
            active_goal={"_persistent_id": "g", "_persistent_version": 1},
        )
    assert not called
    update.assert_not_awaited()
    clear.assert_not_awaited()
    assert not task_executor._heartbeat.start_calls
    assert not task_executor._heartbeat.stop_calls
    assert not _FakePresenter.instances
    assert runtime_redis.values[held.key] == held.owner


@pytest.mark.parametrize("resume", [False, True])
async def test_arq_duplicate_preserves_owner_payload_slot_and_run_info(
    monkeypatch, runtime_redis, resume
):
    from unittest.mock import AsyncMock

    from src.infra.channel.chat_lease import ChatLease
    from src.infra.task import arq_worker
    from tests.infra.task.test_arq_worker import _FakeLimiter, _FakePayloadStore
    from tests.infra.task.test_executor_startup_latency import _executor

    task_executor = _executor(monkeypatch)
    owner_info = {"agent_id": "owner", "trace_id": "owner-trace"}
    task_executor._run_info["r"] = owner_info
    manager = SimpleNamespace(
        _ensure_executor=lambda: task_executor, _run_info=task_executor._run_info
    )
    limiter = _FakeLimiter()
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: manager)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)
    monkeypatch.setattr(
        arq_worker, "_acquire_hitl_resume_startup_lock", AsyncMock(return_value="startup")
    )
    monkeypatch.setattr(arq_worker, "_release_hitl_resume_startup_lock", AsyncMock())
    monkeypatch.setattr(arq_worker, "wait_for_hitl_source_release", AsyncMock(return_value=True))
    monkeypatch.setattr(arq_worker, "_run_watchdog_timeout", lambda: None)
    statuses = AsyncMock()
    monkeypatch.setattr(task_executor, "_update_session_status", statuses)

    async def source(*args, **kwargs):
        yield {"event": "message:chunk", "data": {"content": "must not run"}}

    monkeypatch.setattr(arq_worker, "_resolve_executor", lambda key: source)
    held = ChatLease("goal:runner:g:r", ttl=60)
    assert await held.acquire()
    payload = {
        "session_id": "s",
        "run_id": "r",
        "user_id": "u",
        "agent_id": "fast",
        "message": "continue",
        "executor_key": "agent_stream",
        "active_goal": {"_persistent_id": "g", "_persistent_version": 1},
    }
    if resume:
        payload["hitl_resume"] = {"approval_id": "approval"}
    store = _FakePayloadStore(payload)
    if resume:
        from arq import Retry

        with pytest.raises(Retry) as retry:
            await arq_worker.run_agent_task({"payload_store": store}, "r")
        assert 60 <= retry.value.defer_score / 1000 <= 65
    else:
        await arq_worker.run_agent_task({"payload_store": store}, "r")
    assert not store.deleted
    assert not limiter.acquire_calls
    assert not limiter.release_calls
    assert manager._run_info["r"] is owner_info
    statuses.assert_not_awaited()
    assert runtime_redis.values[held.key] == held.owner


@pytest.mark.parametrize("action", ["pause", "clear"])
async def test_ordinary_chat_after_goal_can_recover_but_old_goal_run_cannot(action):
    from src.infra.goal_runtime import restore_goal_for_run
    from src.infra.task.exceptions import TaskInterruptedError

    service = GoalService(Store())
    created = await service.create(
        "s", "u", PersistentGoalCreate(objective="finish", rubric="tests")
    )
    run = await service.reserve("s", "u", created.version)
    await service.control("s", "u", action)
    session = SimpleNamespace(id="s", user_id="u", metadata={"persistent_goal_id": created.id})
    assert await restore_goal_for_run(session, "ordinary-chat", service=service) is None
    with pytest.raises(TaskInterruptedError):
        await restore_goal_for_run(session, run.current_run_id, service=service)


async def test_local_submission_acquires_goal_lease_before_metadata_and_message(
    monkeypatch, runtime_redis
):
    from unittest.mock import AsyncMock

    from src.infra.channel.chat_lease import ChatLease
    from src.infra.task.exceptions import TaskInterruptedError
    from src.infra.task.manager import BackgroundTaskManager
    from tests.infra.task.test_arq_submission import _FakeExecutor

    manager = BackgroundTaskManager()
    executor = _FakeExecutor()
    manager._executor = executor
    manager._persist_initial_user_message = AsyncMock()
    manager._release_concurrency = AsyncMock()
    held = ChatLease("goal:runner:g:r", ttl=60)
    assert await held.acquire()
    with pytest.raises(TaskInterruptedError, match="lease"):
        await manager.submit(
            "s",
            "fast",
            "continue",
            "u",
            object(),
            run_id="r",
            active_goal={"_persistent_id": "g", "_persistent_version": 1},
            write_user_message_immediately=True,
        )
    assert not executor.ensure_calls
    assert not executor.status_calls
    assert not executor.run_calls
    manager._persist_initial_user_message.assert_not_awaited()
    assert not manager._tasks
    assert runtime_redis.values[held.key] == held.owner


async def test_local_goal_lease_transfers_to_task_until_completion(monkeypatch, runtime_redis):
    import asyncio
    from unittest.mock import AsyncMock

    from src.infra.task.manager import BackgroundTaskManager
    from tests.infra.task.test_arq_submission import _BlockingExecutor

    service = GoalService(Store())
    await service.create("s", "u", PersistentGoalCreate(objective="finish", rubric="tests"))
    goal = await service.attach_user_run("s", "u", "r")
    monkeypatch.setattr("src.infra.goal_runtime.GoalService", lambda: service)
    manager = BackgroundTaskManager()
    executor = _BlockingExecutor()
    manager._executor = executor
    manager._release_concurrency = AsyncMock()
    await manager.submit(
        "s",
        "fast",
        "continue",
        "u",
        object(),
        run_id="r",
        active_goal={"_persistent_id": goal.id, "_persistent_version": goal.version},
    )
    task = manager._tasks["r"]
    try:
        await asyncio.wait_for(executor.started.wait(), 1)
        assert f"goal:runner:{goal.id}:r" in runtime_redis.values
        executor.release.set()
        await task
        await asyncio.sleep(0)
        await manager._drain_release_tasks()
        assert f"goal:runner:{goal.id}:r" not in runtime_redis.values
    finally:
        executor.release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_duplicate_local_task_callback_never_releases_owner_slot():
    import asyncio
    from unittest.mock import AsyncMock

    from src.infra.goal_runtime import GoalRunAlreadyOwnedError
    from src.infra.task.manager import BackgroundTaskManager

    manager = BackgroundTaskManager()
    manager._release_concurrency = AsyncMock()

    async def duplicate():
        raise GoalRunAlreadyOwnedError("lease owned")

    task = asyncio.create_task(duplicate())
    await asyncio.gather(task, return_exceptions=True)
    manager._tasks["r"] = task
    manager._run_info["r"] = {"user_id": "u"}
    manager._on_task_done("r", task)
    await manager._drain_release_tasks()
    manager._release_concurrency.assert_not_awaited()


async def test_replaced_goal_keeps_old_human_run_fenced_during_recovery():
    from src.infra.goal_runtime import restore_goal_for_run
    from src.infra.task.exceptions import TaskInterruptedError

    service = GoalService(Store())
    created = await service.create(
        "s", "u", PersistentGoalCreate(objective="first", rubric="first")
    )
    human = await service.attach_user_run("s", "u", "random-human-run")
    await service.record_usage(
        "s",
        "u",
        human.version,
        human.current_run_id,
        usage=12,
        completed=True,
        expected_goal_id=created.id,
    )
    current = await service.get("s", "u")
    replacement = await service.create(
        "s",
        "u",
        PersistentGoalCreate(objective="new", rubric="new", expected_revision=current.revision),
    )
    session = SimpleNamespace(id="s", user_id="u", metadata={"persistent_goal_id": replacement.id})
    assert replacement.accounting.tokens == 0
    assert replacement.accounting.turns == 0
    with pytest.raises(TaskInterruptedError):
        await restore_goal_for_run(session, human.current_run_id, service=service)
    assert await restore_goal_for_run(session, "new-ordinary-chat", service=service) is None
    assert (
        await service.record_usage(
            "s", "u", human.version, human.current_run_id, usage=20, expected_goal_id=created.id
        )
        is None
    )
