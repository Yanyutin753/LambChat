from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.task import recovery


@pytest.mark.parametrize("recorded_total", [12, 112])
async def test_restart_preserves_handoff_request_files_and_latest_usage(
    monkeypatch, recorded_total
):
    """Covers both pre-Search startup failure and a later interrupted execution segment."""
    submit = AsyncMock(return_value=("run-1", "trace-1"))
    service = recovery.TaskRecoveryService(
        storage=SimpleNamespace(),
        run_info={},
        heartbeat=None,
        ensure_executor=lambda: None,
        submit_task=submit,
        mark_run_failed=AsyncMock(),
    )
    monkeypatch.setattr(service, "get_preferred_language", AsyncMock(return_value="zh"))
    monkeypatch.setattr(recovery.settings, "TASK_BACKEND", "local")
    monkeypatch.setattr(recovery, "_registered_agent_ids", lambda: {"quick", "search", "team"})
    monkeypatch.setattr(recovery, "get_registered_executor", lambda _: AsyncMock())
    monkeypatch.setattr("src.infra.goal_runtime.restore_goal_for_run", AsyncMock(return_value=None))
    monkeypatch.setattr(
        recovery,
        "get_concurrency_limiter",
        lambda: SimpleNamespace(
            try_acquire_run_slot=AsyncMock(return_value=True),
            release=AsyncMock(),
        ),
    )
    monkeypatch.setattr(
        recovery,
        "get_trace_storage",
        lambda: SimpleNamespace(
            get_last_trace_event=AsyncMock(
                return_value={
                    "data": {
                        "total_tokens": recorded_total,
                        "cache_read_tokens": 8,
                    }
                }
            ),
        ),
    )
    files = [{"key": "owned-file", "name": "预算.xlsx"}]
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        name="验收",
        metadata={
            "current_run_id": "run-1",
            "agent_id": "quick",
            "agent_options": {"model_id": "model-1"},
            "agent_handoff": {
                "run_id": "run-1",
                "agent_id": "search",
                "message_id": "handoff-user:run-1",
                "run_started_at": 100.0,
                "prior_usage": {"total_tokens": 12},
                "attachments": files,
            },
        },
    )
    result = await service.submit_seamless_resume(session, "run-1", "trace-1", "server_restart")
    assert result["success"] is True
    assert submit.await_args.args[:2] == ("session-1", "search")
    kwargs = submit.await_args.kwargs
    assert kwargs["attachments"] == files
    assert kwargs["user_message_written"] is True
    assert kwargs["trace_id"] == "trace-1"
    carry = kwargs["agent_options"]["_handoff_usage"]
    assert carry["prior_usage"]["total_tokens"] == recorded_total
    assert carry["prior_usage"]["cache_read_tokens"] == 8
    assert carry["run_started_at"] == 100.0
    assert (
        "message_id" not in carry
    )  # Do not replace the checkpointed request with a recovery instruction.
