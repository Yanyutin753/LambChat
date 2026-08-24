from __future__ import annotations

"""Server-restart recovery must persist an error event, not only trace metadata.

Production symptom: traces interrupted by an instance restart ended up with
status="error" and metadata.error="Task interrupted (instance unavailable)"
but no error event in the event stream — the run history showed a failure
with no explanation because the UI renders error events, not trace metadata.
"""

from types import SimpleNamespace

import pytest

from src.infra.task import recovery as recovery_module
from src.infra.task.recovery import TaskRecoveryService


class _FakeStorage:
    def __init__(self, session=None) -> None:
        self.session = session
        self.updates: list[tuple[str, object]] = []

    async def update(self, session_id, session_update) -> None:
        self.updates.append((session_id, session_update))


class _FakeExecutor:
    def __init__(self) -> None:
        self.status_updates: list[tuple] = []

    async def _update_session_status(self, session_id, status, reason=None, run_id=None):
        self.status_updates.append((session_id, status, reason, run_id))


class _FakeTraceStorage:
    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self.completions: list[dict] = []
        self.collection = SimpleNamespace(find=lambda query, projection=None: _FakeCursor(trace_id))

    async def complete_trace(self, trace_id, status="completed", metadata=None, **kwargs):
        self.completions.append({"trace_id": trace_id, "status": status, "metadata": metadata})
        return True


class _FakeCursor:
    def __init__(self, trace_id: str) -> None:
        self._docs = [{"trace_id": trace_id}]

    def sort(self, key, direction=None):
        return self

    def limit(self, limit):
        return self

    async def to_list(self, length=None):
        return list(self._docs)

    async def complete_trace(self, trace_id, status="completed", metadata=None, **kwargs):
        self.completions.append({"trace_id": trace_id, "status": status, "metadata": metadata})
        return True


class _FakeDualWriter:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def write_event(self, **kwargs):
        self.events.append(kwargs)
        return True

    async def flush_mongo_buffer(self) -> None:
        self.flushed = True


def _make_service(storage, executor, trace_storage):
    return TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=SimpleNamespace(check_exists=lambda run_id: False),
        ensure_executor=lambda: executor,
        submit_task=_stub_submit,
        mark_run_failed=_stub_mark_failed,
    )


async def _stub_submit(*_args, **_kwargs):
    return ("", "")


async def _stub_mark_failed(*_args, **_kwargs):
    return None


@pytest.mark.asyncio
async def test_mark_run_failed_writes_error_event_before_completing_trace(monkeypatch):
    session = SimpleNamespace(id="session-1", user_id="user-1", metadata={})
    storage = _FakeStorage(session)
    executor = _FakeExecutor()
    trace_storage = _FakeTraceStorage("trace-1")
    dual_writer = _FakeDualWriter()
    monkeypatch.setattr(recovery_module, "get_trace_storage", lambda: trace_storage)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer", lambda: dual_writer
    )
    service = _make_service(storage, executor, trace_storage)

    await service.mark_run_failed(
        "run-1", "Task interrupted (instance unavailable)", session
    )

    assert len(dual_writer.events) == 1
    event = dual_writer.events[0]
    assert event["event_type"] == "error"
    assert event["trace_id"] == "trace-1"
    assert event["run_id"] == "run-1"
    assert event["session_id"] == "session-1"
    assert "interrupted" in event["data"]["error"]

    # trace completion still runs and keeps its metadata
    assert trace_storage.completions[0]["status"] == "error"
    assert trace_storage.completions[0]["metadata"]["error_code"] == "server_restart"
