"""A terminal Goal/run must not be rearmed or have its final stream stripped."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra import goal_runtime
from src.infra.task import recovery
from src.infra.task.session_status import TaskSessionStatusMixin
from src.infra.task.state_machine import TaskStateMachine


class Storage:
    def __init__(self, status="failed"):
        self.metadata = {
            "current_run_id": "goal-run",
            "task_status": status,
            "task_error": "Original failure",
            "task_error_code": "server_restart",
            "task_recoverable": status == "failed",
            "persistent_goal_id": "g",
        }
        self.updates = []
        self.claims = 0

    async def get_by_session_id(self, session_id):
        return SimpleNamespace(
            id="s", user_id="u", agent_id="search", name="owned", metadata=dict(self.metadata)
        )

    async def update_metadata_for_run(
        self, session_id, run_id, metadata, *, expected_statuses=None, expected_recovery_token=None
    ):
        if self.metadata["current_run_id"] != run_id:
            return False
        if expected_statuses is not None and self.metadata["task_status"] not in expected_statuses:
            return False
        if (
            expected_recovery_token is not None
            and self.metadata.get("recovery_token") != expected_recovery_token
        ):
            return False
        self.updates.append(dict(metadata))
        self.metadata.update(metadata)
        return True

    async def claim_run_recovery(
        self, session_id, run_id, metadata, *, expected_recovery_token=None
    ):
        self.claims += 1
        return await self.update_metadata_for_run(
            session_id, run_id, metadata, expected_recovery_token=expected_recovery_token
        )


class Executor(TaskSessionStatusMixin):
    def __init__(self, storage):
        self._storage = storage
        self._state_machine = TaskStateMachine()

    def _schedule_idle_pause_check(self, session_id):
        pass


class Redis:
    async def set(self, *args, **kwargs):
        return True

    async def eval(self, *args):
        return 1


def setup(monkeypatch, status="failed"):
    storage = Storage(status)
    executor = Executor(storage)
    dispatch = AsyncMock(return_value=("goal-run", "trace"))
    service = recovery.TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=SimpleNamespace(is_stale=AsyncMock(return_value=True)),
        ensure_executor=lambda: executor,
        submit_task=dispatch,
        mark_run_failed=AsyncMock(),
    )
    service._mark_run_failed = AsyncMock(wraps=service.mark_run_failed)
    service._strip_terminal_stream_events = AsyncMock()
    service.get_preferred_language = AsyncMock(return_value="en")
    reopen = AsyncMock()
    cursor = SimpleNamespace(
        sort=lambda *args: cursor, limit=lambda *args: cursor, to_list=AsyncMock(return_value=[])
    )
    monkeypatch.setattr(recovery, "get_redis_client", Redis)
    monkeypatch.setattr(recovery, "_lookup_trace_id_for_run", AsyncMock(return_value="trace"))
    monkeypatch.setattr(
        recovery,
        "get_trace_storage",
        lambda: SimpleNamespace(
            reopen_interrupted_trace=reopen, collection=SimpleNamespace(find=lambda *args: cursor)
        ),
    )
    monkeypatch.setattr(recovery, "get_registered_executor", lambda key: object())
    monkeypatch.setattr(recovery, "_resolve_recovery_agent_id", lambda *args: "search")
    monkeypatch.setattr(recovery.settings, "TASK_BACKEND", "local")
    monkeypatch.setattr(
        "src.infra.websocket.get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=AsyncMock()),
    )
    return service, storage, dispatch, reopen


def goal(status="active"):
    return SimpleNamespace(
        id="g",
        version=1,
        status=status,
        current_run_id="goal-run",
        objective="finish",
        rubric="strict",
        run_accounting=[SimpleNamespace(run_id="goal-run")],
    )


@pytest.mark.parametrize(
    "status", ["completed", "failed", "cancelled", "expired", "waiting_human", "cancelling"]
)
async def test_shutdown_preserves_terminal_or_human_controlled_run(monkeypatch, status):
    service, storage, _, _ = setup(monkeypatch, status)
    before = dict(storage.metadata)
    await service.mark_run_recoverable_failure("s", "goal-run", "Server shutdown")
    assert storage.metadata == before
    assert storage.updates == []


@pytest.mark.parametrize("status", ["running", "queued", "pending", "starting", "recovering"])
async def test_shutdown_marks_active_run_recoverable_in_one_atomic_write(monkeypatch, status):
    service, storage, _, _ = setup(monkeypatch, status)
    await service.mark_run_recoverable_failure("s", "goal-run", "Server shutdown")
    assert len(storage.updates) == 1
    assert storage.updates[0]["task_status"] == "failed"
    assert storage.updates[0]["task_recoverable"] is True
    assert storage.updates[0]["task_error_code"] == "server_restart"
    assert storage.updates[0]["interrupted_run_id"] == "goal-run"


@pytest.mark.parametrize("status", ["paused", "blocked", "completed", "cleared", "superseded"])
async def test_stopped_goal_refuses_recovery_before_claim_trace_or_stream_mutation(
    monkeypatch, status
):
    service, storage, dispatch, reopen = setup(monkeypatch)
    value = goal(status)
    if status == "superseded":
        value.status = "active"
        value.current_run_id = "new-human"
    monkeypatch.setattr(
        goal_runtime, "GoalService", lambda: SimpleNamespace(get=AsyncMock(return_value=value))
    )
    result = await service.resume_interrupted_run(
        await storage.get_by_session_id("s"), "goal-run", "server_restart"
    )
    assert result["success"] is False and result["code"] == "task_recovery_not_available"
    assert storage.claims == 0
    assert storage.metadata["task_recoverable"] is False
    assert storage.metadata["task_error"] == "Original failure"
    reopen.assert_not_awaited()
    service._strip_terminal_stream_events.assert_not_awaited()
    dispatch.assert_not_awaited()


async def test_goal_pause_after_recovery_claim_is_not_rearmed(monkeypatch):
    service, storage, dispatch, _ = setup(monkeypatch)
    get = AsyncMock(side_effect=[goal(), goal("paused")])
    monkeypatch.setattr(goal_runtime, "GoalService", lambda: SimpleNamespace(get=get))
    result = await service.resume_interrupted_run(
        await storage.get_by_session_id("s"), "goal-run", "server_restart"
    )
    assert result["success"] is False and result["code"] == "task_recovery_not_available"
    assert storage.metadata["task_recoverable"] is False
    assert storage.metadata["task_error"] == "Original failure"
    assert storage.metadata["task_error_code"] == "server_restart"
    service._strip_terminal_stream_events.assert_not_awaited()
    dispatch.assert_not_awaited()


async def test_temporary_goal_storage_failure_keeps_recovery_retryable_without_trace_changes(
    monkeypatch,
):
    service, storage, dispatch, reopen = setup(monkeypatch)
    monkeypatch.setattr(
        goal_runtime,
        "GoalService",
        lambda: SimpleNamespace(
            get=AsyncMock(side_effect=RuntimeError("temporary storage outage"))
        ),
    )
    result = await service.resume_interrupted_run(
        await storage.get_by_session_id("s"), "goal-run", "server_restart"
    )
    assert result["success"] is False
    assert storage.metadata["task_recoverable"] is True
    reopen.assert_not_awaited()
    service._strip_terminal_stream_events.assert_not_awaited()
    dispatch.assert_not_awaited()


async def test_active_goal_still_recovers_under_existing_execution_guard(monkeypatch):
    service, storage, dispatch, reopen = setup(monkeypatch)
    monkeypatch.setattr(
        goal_runtime, "GoalService", lambda: SimpleNamespace(get=AsyncMock(return_value=goal()))
    )
    result = await service.resume_interrupted_run(
        await storage.get_by_session_id("s"), "goal-run", "server_restart"
    )
    assert result["success"] is True
    assert dispatch.call_args.kwargs["active_goal"]["_persistent_id"] == "g"
    reopen.assert_not_awaited()
    assert dispatch.call_args.kwargs["recovery_claim"]["token"]


async def test_ordinary_human_run_after_completed_goal_can_still_recover(monkeypatch):
    service, storage, dispatch, _ = setup(monkeypatch)
    storage.metadata["current_run_id"] = "human-after-goal"
    completed = goal("completed")
    dispatch.return_value = ("human-after-goal", "trace")
    monkeypatch.setattr(
        goal_runtime, "GoalService", lambda: SimpleNamespace(get=AsyncMock(return_value=completed))
    )
    result = await service.resume_interrupted_run(
        await storage.get_by_session_id("s"), "human-after-goal", "server_restart"
    )
    assert result["success"] is True
    assert "active_goal" not in dispatch.call_args.kwargs


@pytest.mark.parametrize(
    "terminal", ["completed", "cancelled", "failed", "waiting_human", "cancelling"]
)
async def test_shutdown_atomic_predicate_preserves_same_run_terminal_race(monkeypatch, terminal):
    from tests.api.routes.test_persistent_goal_hitl import SessionCollection, actual_storage

    collection = SessionCollection()
    storage = actual_storage(monkeypatch, collection)
    collection.doc["metadata"].update(current_run_id="goal-run", task_status="running")
    original = collection.update_one

    async def finish_before_write(query, update):
        collection.doc["metadata"].update(task_status=terminal, task_error="Final diagnostic")
        return await original(query, update)

    collection.update_one = finish_before_write
    service, _, _, _ = setup(monkeypatch)
    service._storage = storage
    await service.mark_run_recoverable_failure(collection.session_id, "goal-run", "Server shutdown")
    assert collection.doc["metadata"]["task_status"] == terminal
    assert collection.doc["metadata"]["task_error"] == "Final diagnostic"
    assert "interrupted_run_id" not in collection.doc["metadata"]


@pytest.mark.parametrize("retryable", [False, True])
async def test_late_admission_restores_only_its_claim_and_original_diagnostics(
    monkeypatch, retryable
):
    service, storage, _, _ = setup(monkeypatch)
    claim = {"token": "old", "metadata": dict(storage.metadata)}
    storage.metadata.update(task_status="starting", task_error=None, recovery_token="old")
    await recovery.restore_recovery_claim(storage, "s", "goal-run", claim, recoverable=retryable)
    assert storage.metadata["task_status"] == "failed"
    assert storage.metadata["task_error"] == "Original failure"
    assert storage.metadata["task_recoverable"] is retryable
    storage.metadata.update(task_status="starting", recovery_token="replacement")
    before = dict(storage.metadata)
    await recovery.restore_recovery_claim(storage, "s", "goal-run", claim, recoverable=retryable)
    assert storage.metadata == before


@pytest.mark.parametrize("terminal", ["completed", "cancelled"])
async def test_terminal_trace_never_loses_terminal_stream(monkeypatch, terminal):
    service, storage, _, reopen = setup(monkeypatch)
    claim = {"token": "claim", "metadata": dict(storage.metadata)}
    storage.metadata.update(task_status="starting", recovery_token="claim")
    reopen.return_value = False
    trace = SimpleNamespace(
        reopen_interrupted_trace=reopen,
        collection=SimpleNamespace(find_one=AsyncMock(return_value={"status": terminal})),
    )
    monkeypatch.setattr(recovery, "get_trace_storage", lambda: trace)
    strip = AsyncMock()
    monkeypatch.setattr(recovery, "strip_terminal_stream_events", strip)
    with pytest.raises(goal_runtime.GoalRunAdmissionError):
        await recovery.prepare_interrupted_recovery(storage, "s", "goal-run", "trace", claim)
    strip.assert_not_awaited()


@pytest.mark.parametrize("temporary", [False, True])
async def test_final_executor_guard_rejects_before_trace_or_stream_changes(monkeypatch, temporary):
    from contextlib import asynccontextmanager

    from src.infra.task.executor import TaskExecutor

    service, storage, _, reopen = setup(monkeypatch)
    claim = {"token": "claim", "metadata": dict(storage.metadata)}
    storage.metadata.update(task_status="pending", task_error=None, recovery_token="claim")

    @asynccontextmanager
    async def lease(*args, **kwargs):
        yield None

    monkeypatch.setattr(goal_runtime, "goal_run_lease", lease)
    failure = (
        RuntimeError("temporary storage failure")
        if temporary
        else goal_runtime.GoalRunAdmissionError("paused")
    )
    monkeypatch.setattr(goal_runtime, "validate_goal_admission", AsyncMock(side_effect=failure))
    prepare = AsyncMock()
    monkeypatch.setattr(recovery, "prepare_interrupted_recovery", prepare)
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    with pytest.raises(type(failure)):
        await executor.run_task(
            "s",
            "goal-run",
            "search",
            "resume",
            "u",
            AsyncMock(),
            active_goal={"_persistent_id": "g"},
            interrupted_resume=True,
            recovery_claim=claim,
            existing_trace_id="trace",
        )
    assert storage.metadata["task_recoverable"] is temporary
    assert storage.metadata["task_error"] == "Original failure"
    assert storage.metadata["task_error_code"] == "server_restart"
    prepare.assert_not_awaited()
    reopen.assert_not_awaited()


async def test_real_storage_rejects_old_recovery_claim_at_atomic_write(monkeypatch):
    from tests.api.routes.test_persistent_goal_hitl import SessionCollection, actual_storage

    collection = SessionCollection()
    storage = actual_storage(monkeypatch, collection)
    collection.doc["metadata"].update(
        current_run_id="goal-run", task_status="starting", recovery_token="old"
    )
    claim = {"token": "old", "metadata": {"task_error": "Original failure"}}
    original = collection.update_one

    async def replace_claim_before_write(query, update):
        collection.doc["metadata"].update(recovery_token="new", task_error="Replacement")
        return await original(query, update)

    collection.update_one = replace_claim_before_write
    await recovery.restore_recovery_claim(
        storage, collection.session_id, "goal-run", claim, recoverable=False
    )
    assert collection.doc["metadata"]["task_error"] == "Replacement"
    assert collection.doc["metadata"]["recovery_token"] == "new"


async def test_goal_revoked_during_starting_admission_preserves_trace_and_diagnostics(monkeypatch):
    from contextlib import asynccontextmanager

    from src.infra.task.executor import TaskExecutor

    _, storage, _, reopen = setup(monkeypatch)
    claim = {"token": "claim", "metadata": dict(storage.metadata)}
    storage.metadata.update(task_status="pending", task_error=None, recovery_token="claim")

    @asynccontextmanager
    async def lease(*args, **kwargs):
        yield None

    admission = AsyncMock(
        side_effect=[None, goal_runtime.GoalRunAdmissionError("paused during admission")]
    )
    monkeypatch.setattr(goal_runtime, "goal_run_lease", lease)
    monkeypatch.setattr("src.infra.scheduler.conversation.conversation_submission", lease)
    monkeypatch.setattr(goal_runtime, "validate_goal_admission", admission)
    monkeypatch.setattr(
        "src.infra.task.background_admission.validate_background_resume",
        AsyncMock(return_value=False),
    )
    prepare = AsyncMock()
    monkeypatch.setattr(recovery, "prepare_interrupted_recovery", prepare)
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    with pytest.raises(goal_runtime.GoalRunAdmissionError):
        await executor.run_task(
            "s",
            "goal-run",
            "search",
            "resume",
            "u",
            AsyncMock(),
            active_goal={"_persistent_id": "g"},
            interrupted_resume=True,
            recovery_claim=claim,
            existing_trace_id="trace",
        )
    assert admission.await_count == 2
    assert storage.metadata["task_recoverable"] is False
    assert storage.metadata["task_error"] == "Original failure"
    prepare.assert_not_awaited()
    reopen.assert_not_awaited()


@pytest.mark.parametrize("temporary", [False, True])
async def test_arq_admission_refusal_preserves_trace_and_retry_classification(
    monkeypatch, temporary
):
    from contextlib import asynccontextmanager

    from src.infra.task import arq_worker

    _, storage, _, reopen = setup(monkeypatch)
    claim = {"token": "claim", "metadata": dict(storage.metadata)}
    storage.metadata.update(task_status="recovering", task_error=None, recovery_token="claim")
    payload = {
        "session_id": "s",
        "user_id": "u",
        "run_id": "goal-run",
        "active_goal": {"_persistent_id": "g"},
        "interrupted_resume": True,
        "recovery_claim": claim,
    }
    store = SimpleNamespace(load=AsyncMock(return_value=payload), delete=AsyncMock())

    @asynccontextmanager
    async def lease(*args, **kwargs):
        yield None

    failure = (
        RuntimeError("temporary storage failure")
        if temporary
        else goal_runtime.GoalRunAdmissionError("paused")
    )
    monkeypatch.setattr(goal_runtime, "goal_run_lease", lease)
    monkeypatch.setattr(goal_runtime, "validate_goal_admission", AsyncMock(side_effect=failure))
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: SimpleNamespace(storage=storage))
    run = AsyncMock()
    monkeypatch.setattr(arq_worker, "_run_agent_payload", run)
    if temporary:
        with pytest.raises(RuntimeError):
            await arq_worker.run_agent_task({"payload_store": store}, "dispatch")
        store.delete.assert_not_awaited()
    else:
        await arq_worker.run_agent_task({"payload_store": store}, "dispatch")
        store.delete.assert_awaited_once_with("dispatch")
    assert storage.metadata["task_recoverable"] is temporary
    assert storage.metadata["task_error"] == "Original failure"
    run.assert_not_awaited()
    reopen.assert_not_awaited()


@pytest.mark.parametrize(
    "terminal", ["completed", "cancelled", "failed", "waiting_human", "cancelling"]
)
async def test_actual_recovery_claim_predicate_rejects_same_run_terminal_race(
    monkeypatch, terminal
):
    from tests.api.routes.test_persistent_goal_hitl import SessionCollection, actual_storage

    class Collection(SessionCollection):
        def matches(self, query):
            for key, expected in query.items():
                if key == "$or":
                    if not any(self.matches(item) for item in expected):
                        return False
                    continue
                actual = self.doc
                for part in key.split("."):
                    actual = actual.get(part) if isinstance(actual, dict) else None
                if isinstance(expected, dict):
                    for operation, value in expected.items():
                        if operation == "$in" and actual not in value:
                            return False
                        if operation == "$nin" and actual in value:
                            return False
                        if operation == "$ne" and actual == value:
                            return False
                elif actual != expected:
                    return False
            return True

    collection = Collection()
    storage = actual_storage(monkeypatch, collection)
    collection.doc["metadata"].update(
        current_run_id="goal-run", task_status="recovering", recovery_token="claim"
    )
    original = collection.update_one

    async def finish_before_write(query, update):
        collection.doc["metadata"].update(
            task_status=terminal, task_recoverable=False, task_error="Final diagnostic"
        )
        return await original(query, update)

    collection.update_one = finish_before_write
    admitted = await storage.claim_run_recovery(
        collection.session_id,
        "goal-run",
        {"task_status": "pending"},
        expected_recovery_token="claim",
    )
    assert admitted is False
    assert collection.doc["metadata"]["task_status"] == terminal
    assert collection.doc["metadata"]["task_error"] == "Final diagnostic"


async def test_stopped_goal_retires_stale_running_session_without_claim(monkeypatch):
    service, storage, dispatch, reopen = setup(monkeypatch, "running")
    monkeypatch.setattr(
        goal_runtime,
        "GoalService",
        lambda: SimpleNamespace(get=AsyncMock(return_value=goal("paused"))),
    )
    result = await service.resume_interrupted_run(
        await storage.get_by_session_id("s"), "goal-run", "server_restart"
    )
    assert result["code"] == "task_recovery_not_available"
    assert storage.metadata["task_status"] == "failed"
    assert storage.metadata["task_recoverable"] is False
    assert storage.metadata["task_error"] == "Original failure"
    assert storage.claims == 0
    dispatch.assert_not_awaited()
    reopen.assert_not_awaited()


@pytest.mark.parametrize("mutation", ["pause", "new-human"])
async def test_preparation_fence_blocks_goal_control_and_new_turn_during_trace_io(
    monkeypatch, mutation
):
    import asyncio
    from contextlib import asynccontextmanager

    from src.infra.scheduler.conversation import conversation_submission
    from src.infra.task.executor import TaskExecutor
    from src.kernel.errors import AppError

    _, storage, _, _ = setup(monkeypatch)
    claim = {"token": "claim", "metadata": dict(storage.metadata)}
    storage.metadata.update(task_status="pending", recovery_token="claim")
    entered, release = asyncio.Event(), asyncio.Event()
    held = set()

    class Lease:
        def __init__(self, key, **kwargs):
            self.key = key

        async def acquire(self):
            if self.key in held:
                return False
            held.add(self.key)
            return True

        async def renew(self):
            return True

        async def release(self):
            held.remove(self.key)

    @asynccontextmanager
    async def run_lease(*args, **kwargs):
        yield None

    async def reopen(_trace):
        entered.set()
        await release.wait()
        return True

    class PreparedError(Exception):
        pass

    original_prepare = recovery.prepare_interrupted_recovery

    async def prepare(*args):
        await original_prepare(*args)
        raise PreparedError()

    strip = AsyncMock()
    monkeypatch.setattr("src.infra.channel.chat_lease.ChatLease", Lease)
    monkeypatch.setattr(goal_runtime, "goal_run_lease", run_lease)
    monkeypatch.setattr(goal_runtime, "validate_goal_admission", AsyncMock())
    monkeypatch.setattr(
        "src.infra.task.background_admission.validate_background_resume",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        recovery, "get_trace_storage", lambda: SimpleNamespace(reopen_interrupted_trace=reopen)
    )
    monkeypatch.setattr(recovery, "strip_terminal_stream_events", strip)
    monkeypatch.setattr(recovery, "prepare_interrupted_recovery", prepare)
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    task = asyncio.create_task(
        executor.run_task(
            "s",
            "goal-run",
            "search",
            "resume",
            "u",
            AsyncMock(),
            interrupted_resume=True,
            recovery_claim=claim,
            existing_trace_id="trace",
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(AppError):
            async with conversation_submission("s", "u", allow_busy=True):
                storage.metadata.update(current_run_id=mutation, task_status="cancelled")
        assert storage.metadata["current_run_id"] == "goal-run"
        strip.assert_not_awaited()
        release.set()
        with pytest.raises(PreparedError):
            await task
        strip.assert_awaited_once_with("s", "goal-run")
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)
    assert not held


async def test_failed_terminal_stream_cleanup_keeps_execution_retryable(monkeypatch):
    from contextlib import asynccontextmanager

    from src.infra.task.executor import TaskExecutor

    _, storage, _, reopen = setup(monkeypatch)
    claim = {"token": "claim", "metadata": dict(storage.metadata)}
    storage.metadata.update(task_status="pending", recovery_token="claim")
    reopen.return_value = True

    @asynccontextmanager
    async def lease(*args, **kwargs):
        yield None

    monkeypatch.setattr(goal_runtime, "goal_run_lease", lease)
    monkeypatch.setattr(goal_runtime, "validate_goal_admission", AsyncMock())
    monkeypatch.setattr("src.infra.scheduler.conversation.conversation_submission", lease)
    monkeypatch.setattr(
        "src.infra.task.background_admission.validate_background_resume",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        recovery, "strip_terminal_stream_events", AsyncMock(side_effect=RuntimeError("redis down"))
    )
    execute = AsyncMock()
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    with pytest.raises(RuntimeError, match="redis down"):
        await executor.run_task(
            "s",
            "goal-run",
            "search",
            "resume",
            "u",
            execute,
            interrupted_resume=True,
            recovery_claim=claim,
            existing_trace_id="trace",
        )
    assert storage.metadata["task_status"] == "failed"
    assert storage.metadata["task_recoverable"] is True
    assert storage.metadata["task_error"] == "Original failure"
    execute.assert_not_awaited()
