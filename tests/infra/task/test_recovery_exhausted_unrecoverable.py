from __future__ import annotations

"""Regression tests: resume-exhausted termination must not re-arm auto-recovery.

Production symptom (k3s dual pods): a scheduled run failed (upstream content
moderation), auto-recovery resumed it until ``resume_attempts`` hit the cap,
and every later scan loop called mark_run_failed again — which persisted
``task_recoverable=True`` + ``task_error_code="server_restart"``. That is
exactly the predicate ``_is_latest_explicit_system_restart_failure`` matches,
so both pods re-took the recovery lock in circles for hours (~1200 scan hits,
500+ "已在其他实例中启动", 147 lock takeovers, and 553 duplicated
"Resume attempts exhausted" error events appended to one trace).
"""

from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.task import recovery as recovery_module
from src.infra.task.recovery import TaskRecoveryService


class _FakeStorage:
    def __init__(self, session=None) -> None:
        self.session = session
        self.updates: list[tuple[str, Any]] = []

    async def update(self, session_id, session_update) -> None:
        self.updates.append((session_id, session_update))


class _FakeExecutor:
    async def _update_session_status(self, session_id, status, reason=None, run_id=None):
        return None


class _FakeHeartbeat:
    def __init__(self, stale: bool = True) -> None:
        self._stale = stale

    async def is_stale(self, run_id: str) -> bool:
        return self._stale

    async def check_exists(self, run_id: str) -> bool:
        return False


class _FakeRedis:
    async def set(self, key, value, ex=None, nx=False):
        return True

    def eval(self, *args, **kwargs):
        return 1


def _metadata_of(update) -> dict:
    # storage.update 记录为 (session_id, SessionUpdate) 元组
    session_update = update[1] if isinstance(update, tuple) else update
    return session_update.metadata


def _make_service(storage, mark_calls: list[dict]) -> TaskRecoveryService:
    async def _mark_run_failed(run_id, reason, session, **kwargs):
        mark_calls.append({"run_id": run_id, "reason": reason, **kwargs})

    async def _submit(*_args, **_kwargs):
        return ("", "")

    return TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=_FakeHeartbeat(stale=True),
        ensure_executor=lambda: _FakeExecutor(),
        submit_task=_submit,
        mark_run_failed=_mark_run_failed,
    )


@pytest.mark.asyncio
async def test_mark_run_failed_defaults_to_recoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = _FakeStorage()
    service = TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=_FakeHeartbeat(),
        ensure_executor=lambda: _FakeExecutor(),
        submit_task=_stub,
        mark_run_failed=_noop_mark,
    )
    monkeypatch.setattr(recovery_module, "get_trace_storage", _raise_trace_storage_unavailable)

    await service.mark_run_failed("run-1", "Task interrupted", SimpleNamespace(id="s1"))

    assert storage.updates, "session metadata must be persisted"
    assert _metadata_of(storage.updates[0])["task_recoverable"] is True


@pytest.mark.asyncio
async def test_mark_run_failed_can_persist_unrecoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = _FakeStorage()
    service = TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=_FakeHeartbeat(),
        ensure_executor=lambda: _FakeExecutor(),
        submit_task=_stub,
        mark_run_failed=_noop_mark,
    )
    monkeypatch.setattr(recovery_module, "get_trace_storage", _raise_trace_storage_unavailable)

    await service.mark_run_failed(
        "run-1", "Resume attempts exhausted (3)", SimpleNamespace(id="s1"), recoverable=False
    )

    assert _metadata_of(storage.updates[0])["task_recoverable"] is False


@pytest.mark.asyncio
async def test_resume_interrupted_run_marks_exhausted_run_unrecoverable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """达到恢复上限的终止必须让扫描器不再接管（task_recoverable=False）。"""
    from datetime import datetime, timezone

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: _FakeRedis())

    session = SimpleNamespace(
        id="session-1",
        metadata={
            "current_run_id": "run-exhausted",
            "resume_attempts": recovery_module.MAX_SEAMLESS_RESUME_ATTEMPTS,
            "task_status": "recovering",
        },
        agent_id="search",
        updated_at=datetime.now(timezone.utc),
    )
    storage = _FakeStorage(session)
    mark_calls: list[dict] = []
    service = _make_service(storage, mark_calls)

    result = await service.resume_interrupted_run(session, "run-exhausted", "server_restart")

    assert result["success"] is False
    assert "恢复次数已达上限" in result["message"]
    assert mark_calls == [
        {
            "run_id": "run-exhausted",
            "reason": f"Resume attempts exhausted ({recovery_module.MAX_SEAMLESS_RESUME_ATTEMPTS})",
            "recoverable": False,
        }
    ]


async def _stub(*_args, **_kwargs):
    return ("", "")


async def _noop_mark(*_args, **_kwargs):
    return None


async def _raise_trace_storage_unavailable():
    raise RuntimeError("trace storage unavailable in test")
