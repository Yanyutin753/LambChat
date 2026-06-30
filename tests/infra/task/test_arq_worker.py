from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.extensions import InMemoryPluginRuntimeStateStorage
from src.infra.task import arq_worker
from src.infra.task.exceptions import TaskInterruptedError
from src.infra.task.status import TaskStatus
from src.kernel.extensions import (
    PluginRuntime,
    PluginRuntimeStatus,
    build_agent_team_plugin_manifest,
    build_workflow_plugin_manifest,
)


class _FakePayloadStore:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.deleted: list[str] = []

    async def load(self, run_id: str):
        return self.payload if run_id == self.payload["run_id"] else None

    async def delete(self, run_id: str) -> bool:
        self.deleted.append(run_id)
        return True


class _FakeTaskExecutor:
    def __init__(self) -> None:
        self.run_calls: list[dict] = []
        self.status_calls: list[tuple] = []

    async def run_task(self, **kwargs) -> None:
        self.run_calls.append(kwargs)

    async def _update_session_status(self, *args, **kwargs) -> None:
        self.status_calls.append((args, kwargs))


class _CancelledTaskExecutor:
    def __init__(self) -> None:
        self.run_calls: list[dict] = []

    async def run_task(self, **kwargs) -> None:
        self.run_calls.append(kwargs)
        raise asyncio.CancelledError()


class _InterruptedTaskExecutor:
    def __init__(self) -> None:
        self.run_calls: list[dict] = []

    async def run_task(self, **kwargs) -> None:
        self.run_calls.append(kwargs)
        raise TaskInterruptedError("Task interrupted: run_id=run-1")


class _GenericFailingTaskExecutor:
    def __init__(self) -> None:
        self.run_calls: list[dict] = []

    async def run_task(self, **kwargs) -> None:
        self.run_calls.append(kwargs)
        raise RuntimeError("boom")


class _FakeStorage:
    def __init__(self, metadata: dict | None = None) -> None:
        self.metadata = metadata or {}

    async def get_by_session_id(self, session_id: str):
        return SimpleNamespace(metadata=self.metadata)


class _FakeLimiter:
    def __init__(self) -> None:
        self.release_calls: list[tuple[str, str, bool]] = []

    async def release(self, user_id: str, run_id: str, dequeue: bool = True) -> None:
        self.release_calls.append((user_id, run_id, dequeue))


class _FakeWorkflowPluginStorage:
    def __init__(self, status: str = "queued") -> None:
        self.run = SimpleNamespace(
            run_id="wfr-1",
            workflow_id="wf-1",
            version_id="wfv-1",
            owner_user_id="user-1",
            status=status,
        )
        self.events: list[dict] = []
        self.finished: list[dict] = []

    async def get_run(self, run_id: str, *, owner_user_id: str):
        if run_id != self.run.run_id or owner_user_id != self.run.owner_user_id:
            return None
        return self.run

    async def append_run_events(self, *, run, events: list[dict]):
        self.events.extend(events)
        return []

    async def finish_run(self, **kwargs):
        self.finished.append(kwargs)
        self.run.status = kwargs["status"]
        self.run.error = kwargs.get("error")
        return self.run


class _FakeWorkflowPluginService:
    def __init__(
        self,
        storage: _FakeWorkflowPluginStorage,
        calls: list[dict],
        execute_error: Exception | None = None,
    ) -> None:
        self.storage = storage
        self.calls = calls
        self.execute_error = execute_error

    async def execute_existing_run(self, **kwargs) -> None:
        self.calls.append(kwargs)
        if self.execute_error is not None:
            raise self.execute_error


@pytest.mark.asyncio
async def test_worker_settings_validate_distributed_runtime_on_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def _fake_validate(settings):
        calls.append(settings)

    monkeypatch.setattr(arq_worker, "validate_distributed_runtime_settings", _fake_validate)

    await arq_worker.WorkerSettings.on_startup({})

    assert calls == [arq_worker.settings]


@pytest.mark.asyncio
async def test_run_agent_task_loads_payload_and_invokes_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "agent_id": "search",
        "message": "hello",
        "display_message": "hello display",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "user_message_written": True,
        "agent_options": {"model": "test"},
        "team_id": "team-1",
        "active_goal": {"objective": "finish docs", "rubric": "- docs updated"},
    }
    payload_store = _FakePayloadStore(payload)
    task_executor = _FakeTaskExecutor()
    task_manager = SimpleNamespace(
        _run_info={},
        _ensure_executor=lambda: task_executor,
    )

    async def _executor_fn(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: _executor_fn)

    await arq_worker.run_agent_task({"payload_store": payload_store}, "run-1")

    assert task_executor.run_calls
    assert task_executor.run_calls[0]["session_id"] == "session-1"
    assert task_executor.run_calls[0]["existing_trace_id"] == "trace-1"
    assert task_executor.run_calls[0]["executor"] is _executor_fn
    assert task_executor.run_calls[0]["team_id"] == "team-1"
    assert task_executor.run_calls[0]["active_goal"] == {
        "objective": "finish docs",
        "rubric": "- docs updated",
    }
    assert task_manager._run_info == {}
    assert payload_store.deleted == ["run-1"]


@pytest.mark.asyncio
async def test_run_agent_task_imports_default_executor_when_registry_is_cold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "agent_id": "search",
        "message": "hello",
        "display_message": "hello display",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "user_message_written": True,
    }
    payload_store = _FakePayloadStore(payload)
    task_executor = _FakeTaskExecutor()
    limiter = _FakeLimiter()
    task_manager = SimpleNamespace(
        _run_info={},
        _ensure_executor=lambda: task_executor,
    )
    calls = {"registry": 0, "imports": []}

    async def _executor_fn(*args, **kwargs):
        if False:
            yield None

    def _get_registered_executor(key: str):
        calls["registry"] += 1
        return None if calls["registry"] == 1 else _executor_fn

    def _import_module(name: str):
        calls["imports"].append(name)
        return SimpleNamespace()

    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", _get_registered_executor)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)
    monkeypatch.setattr(arq_worker, "import_module", _import_module, raising=False)

    await arq_worker.run_agent_task({"payload_store": payload_store}, "run-1")

    assert calls["imports"] == ["src.api.routes.chat"]
    assert task_executor.run_calls
    assert payload_store.deleted == ["run-1"]
    assert limiter.release_calls == [("user-1", "run-1", True)]


@pytest.mark.asyncio
async def test_run_agent_task_cleans_up_when_executor_is_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "agent_id": "search",
        "message": "hello",
        "display_message": "hello display",
        "user_id": "user-1",
        "executor_key": "missing_executor",
        "user_message_written": True,
    }
    payload_store = _FakePayloadStore(payload)
    task_executor = _FakeTaskExecutor()
    limiter = _FakeLimiter()
    task_manager = SimpleNamespace(
        _run_info={},
        _ensure_executor=lambda: task_executor,
    )

    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: None)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)

    await arq_worker.run_agent_task({"payload_store": payload_store}, "run-1")

    assert task_executor.run_calls == []
    assert task_executor.status_calls
    assert payload_store.deleted == ["run-1"]
    assert limiter.release_calls == [("user-1", "run-1", True)]


@pytest.mark.asyncio
async def test_run_agent_task_rejects_disabled_plugin_owned_agent_at_execution_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import set_plugin_runtime

    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "agent_id": "team",
        "message": "hello",
        "display_message": "hello display",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "user_message_written": True,
    }
    payload_store = _FakePayloadStore(payload)
    task_executor = _FakeTaskExecutor()
    limiter = _FakeLimiter()
    task_manager = SimpleNamespace(
        _run_info={},
        _ensure_executor=lambda: task_executor,
    )
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")

    async def _executor_fn(*args, **kwargs):
        raise AssertionError("disabled plugin-owned agent should not run")
        if False:
            yield None

    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: _executor_fn)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)
    set_plugin_runtime(runtime)

    try:
        await arq_worker.run_agent_task({"payload_store": payload_store}, "run-1")
    finally:
        set_plugin_runtime(None)

    assert task_executor.run_calls == []
    assert task_executor.status_calls
    args, kwargs = task_executor.status_calls[0]
    assert args[0] == "session-1"
    assert args[1] is TaskStatus.FAILED
    assert "agent_team" in args[2]
    assert kwargs == {"run_id": "run-1"}
    assert payload_store.deleted == ["run-1"]
    assert limiter.release_calls == [("user-1", "run-1", True)]
    assert task_manager._run_info == {}


@pytest.mark.asyncio
async def test_run_agent_task_marks_recoverable_and_deletes_payload_when_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "agent_id": "search",
        "message": "hello",
        "display_message": "hello display",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "user_message_written": True,
    }
    payload_store = _FakePayloadStore(payload)
    task_executor = _CancelledTaskExecutor()
    recoverable_failures: list[tuple[str, str, str]] = []
    limiter = _FakeLimiter()

    async def _fake_mark_recoverable_failure(
        session_id: str,
        run_id: str,
        error_message: str,
    ) -> None:
        recoverable_failures.append((session_id, run_id, error_message))

    task_manager = SimpleNamespace(
        _run_info={},
        _ensure_executor=lambda: task_executor,
        _mark_run_recoverable_failure=_fake_mark_recoverable_failure,
    )

    async def _executor_fn(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: _executor_fn)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)

    with pytest.raises(asyncio.CancelledError):
        await arq_worker.run_agent_task({"payload_store": payload_store}, "run-1")

    assert task_executor.run_calls
    assert recoverable_failures == [("session-1", "run-1", "Server shutdown")]
    assert payload_store.deleted == ["run-1"]
    assert limiter.release_calls == [("user-1", "run-1", False)]


@pytest.mark.asyncio
async def test_run_agent_task_does_not_mark_user_cancelled_run_recoverable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "agent_id": "search",
        "message": "hello",
        "display_message": "hello display",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "user_message_written": True,
    }
    payload_store = _FakePayloadStore(payload)
    task_executor = _CancelledTaskExecutor()
    recoverable_failures: list[tuple[str, str, str]] = []
    limiter = _FakeLimiter()

    async def _fake_mark_recoverable_failure(
        session_id: str,
        run_id: str,
        error_message: str,
    ) -> None:
        recoverable_failures.append((session_id, run_id, error_message))

    task_manager = SimpleNamespace(
        _run_info={},
        _ensure_executor=lambda: task_executor,
        _mark_run_recoverable_failure=_fake_mark_recoverable_failure,
        storage=_FakeStorage(
            {
                "current_run_id": "run-1",
                "task_status": "cancelled",
                "task_error_code": "cancelled",
                "task_recoverable": False,
            }
        ),
    )

    async def _executor_fn(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: _executor_fn)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)

    await arq_worker.run_agent_task({"payload_store": payload_store}, "run-1")

    assert task_executor.run_calls
    assert recoverable_failures == []
    assert payload_store.deleted == ["run-1"]
    assert limiter.release_calls == [("user-1", "run-1", True)]


@pytest.mark.asyncio
async def test_run_agent_task_deletes_payload_after_task_interrupted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "agent_id": "search",
        "message": "hello",
        "display_message": "hello display",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "user_message_written": True,
    }
    payload_store = _FakePayloadStore(payload)
    task_executor = _InterruptedTaskExecutor()
    limiter = _FakeLimiter()
    task_manager = SimpleNamespace(
        _run_info={},
        _ensure_executor=lambda: task_executor,
    )

    async def _executor_fn(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: _executor_fn)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)

    await arq_worker.run_agent_task({"payload_store": payload_store}, "run-1")

    assert task_executor.run_calls
    assert payload_store.deleted == ["run-1"]
    assert limiter.release_calls == [("user-1", "run-1", True)]


@pytest.mark.asyncio
async def test_run_agent_task_keeps_payload_for_non_cancel_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "agent_id": "search",
        "message": "hello",
        "display_message": "hello display",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "user_message_written": True,
    }
    payload_store = _FakePayloadStore(payload)
    task_executor = _GenericFailingTaskExecutor()
    task_manager = SimpleNamespace(
        _run_info={},
        _ensure_executor=lambda: task_executor,
    )

    async def _executor_fn(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: _executor_fn)

    with pytest.raises(RuntimeError, match="boom"):
        await arq_worker.run_agent_task({"payload_store": payload_store}, "run-1")

    assert task_executor.run_calls
    assert payload_store.deleted == []


@pytest.mark.asyncio
async def test_run_agent_task_deletes_payload_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "trace-1",
        "agent_id": "search",
        "message": "hello",
        "display_message": "hello display",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "user_message_written": True,
    }
    payload_store = _FakePayloadStore(payload)
    task_executor = _FakeTaskExecutor()
    limiter = _FakeLimiter()
    task_manager = SimpleNamespace(
        _run_info={},
        _ensure_executor=lambda: task_executor,
    )

    async def _executor_fn(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: task_manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: _executor_fn)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)

    await arq_worker.run_agent_task({"payload_store": payload_store}, "run-1")

    assert payload_store.deleted == ["run-1"]
    assert limiter.release_calls == [("user-1", "run-1", True)]


@pytest.mark.asyncio
async def test_run_workflow_task_executes_persisted_workflow_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    storage = InMemoryPluginRuntimeStateStorage()
    await storage.set_override(
        plugin_id="workflow",
        status=PluginRuntimeStatus.ENABLED,
        updated_by="admin-1",
    )

    class _FakeWorkflowService:
        async def execute_existing_run(self, **kwargs) -> None:
            calls.append(kwargs)

    async def _fake_create_workflow_service():
        return _FakeWorkflowService()

    monkeypatch.setattr(
        "src.plugins.workflow.service.create_workflow_service",
        _fake_create_workflow_service,
    )

    await arq_worker.run_workflow_task(
        {"plugin_runtime_state_storage": storage},
        "wfr-1",
        "user-1",
        ["user"],
    )

    assert calls == [
        {
            "run_id": "wfr-1",
            "owner_user_id": "user-1",
            "user_roles": ["user"],
        }
    ]


@pytest.mark.asyncio
async def test_run_workflow_task_rejects_default_disabled_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    fake_storage = _FakeWorkflowPluginStorage()

    async def _fake_create_workflow_service():
        return _FakeWorkflowPluginService(fake_storage, calls)

    monkeypatch.setattr(
        "src.plugins.workflow.service.create_workflow_service",
        _fake_create_workflow_service,
    )

    await arq_worker.run_workflow_task(
        {"plugin_runtime_state_storage": InMemoryPluginRuntimeStateStorage()},
        "wfr-1",
        "user-1",
        ["user"],
    )

    assert calls == []
    assert fake_storage.run.status == "failed"
    assert fake_storage.finished == [
        {
            "run_id": "wfr-1",
            "owner_user_id": "user-1",
            "status": "failed",
            "error": "plugin is not enabled: workflow (disabled)",
        }
    ]
    assert fake_storage.events == [
        {
            "event_type": "run_failed",
            "payload": {"error": "plugin is not enabled: workflow (disabled)"},
        }
    ]


@pytest.mark.asyncio
async def test_run_workflow_task_does_not_crash_when_disabled_failure_mark_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def _fake_create_workflow_service():
        nonlocal calls
        calls += 1
        raise RuntimeError("storage offline")

    monkeypatch.setattr(
        "src.plugins.workflow.service.create_workflow_service",
        _fake_create_workflow_service,
    )

    await arq_worker.run_workflow_task(
        {"plugin_runtime_state_storage": InMemoryPluginRuntimeStateStorage()},
        "wfr-1",
        "user-1",
        ["user"],
    )

    assert calls == 1


@pytest.mark.asyncio
async def test_run_workflow_task_marks_run_failed_when_worker_execution_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    fake_storage = _FakeWorkflowPluginStorage()
    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    runtime.enable_plugin("workflow")

    async def _fake_create_workflow_service():
        return _FakeWorkflowPluginService(
            fake_storage,
            calls,
            execute_error=RuntimeError("storage write failed"),
        )

    monkeypatch.setattr(
        "src.plugins.workflow.service.create_workflow_service",
        _fake_create_workflow_service,
    )

    await arq_worker.run_workflow_task(
        {"plugin_runtime": runtime},
        "wfr-1",
        "user-1",
        ["user"],
    )

    assert calls == [
        {
            "run_id": "wfr-1",
            "owner_user_id": "user-1",
            "user_roles": ["user"],
        }
    ]
    assert fake_storage.run.status == "failed"
    assert fake_storage.finished == [
        {
            "run_id": "wfr-1",
            "owner_user_id": "user-1",
            "status": "failed",
            "error": "workflow_run_worker_failed:storage write failed",
        }
    ]
    assert fake_storage.events == [
        {
            "event_type": "run_failed",
            "payload": {"error": "workflow_run_worker_failed:storage write failed"},
        }
    ]


@pytest.mark.asyncio
async def test_run_workflow_task_uses_injected_enabled_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    fake_storage = _FakeWorkflowPluginStorage()
    runtime = PluginRuntime([build_workflow_plugin_manifest()])
    runtime.enable_plugin("workflow")

    async def _fake_create_workflow_service():
        return _FakeWorkflowPluginService(fake_storage, calls)

    monkeypatch.setattr(
        "src.plugins.workflow.service.create_workflow_service",
        _fake_create_workflow_service,
    )

    await arq_worker.run_workflow_task(
        {"plugin_runtime": runtime},
        "wfr-1",
        "user-1",
        ["user"],
    )

    assert calls == [
        {
            "run_id": "wfr-1",
            "owner_user_id": "user-1",
            "user_roles": ["user"],
        }
    ]
    assert fake_storage.events == []
    assert fake_storage.finished == []
