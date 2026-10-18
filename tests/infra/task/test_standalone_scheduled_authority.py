"""Queued scheduled work must use authority and provider configuration from worker admission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.infra.goal_runtime import GoalRunAdmissionError
from src.infra.task import arq_worker
from src.infra.task.status import TaskStatus
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize("field", ["disabled_tools", "disabled_skills", "disabled_mcp_tools"])
def test_nullable_background_restrictions_preserve_current_denials(field):
    from src.infra.task.background_tasks import apply_background_restrictions
    from src.kernel.schemas.agent import AgentRequest

    request = AgentRequest(message="", **{field: ["denied"]})
    apply_background_restrictions(request, {field: None})
    assert getattr(request, field) == ["denied"]


@pytest.fixture
def queued_schedule():
    session = SimpleNamespace(
        user_id="owner", metadata={"task_status": "queued", "current_run_id": "run"}
    )
    executor = SimpleNamespace(
        _update_session_status=AsyncMock(), _handle_generic_error=AsyncMock()
    )
    manager = SimpleNamespace(
        storage=SimpleNamespace(get_by_session_id=AsyncMock(return_value=session)),
        _ensure_executor=lambda: executor,
    )
    payload = {
        "session_id": "session",
        "run_id": "run",
        "user_id": "owner",
        "agent_id": "quick",
        "agent_options": {"model_id": "model", "_resolved_model_profile": {"api_key": "old-key"}},
    }
    with (
        patch.object(arq_worker, "get_task_manager", return_value=manager),
        patch.object(arq_worker, "_release_concurrency_slot", AsyncMock()) as release,
        patch(
            "src.infra.session.manager.SessionManager.get_session", AsyncMock(return_value=session)
        ),
    ):
        yield payload, executor, release


async def test_worker_rejects_chat_permission_revoked_after_queueing(queued_schedule):
    payload, executor, release = queued_schedule
    owner = TokenPayload(sub="owner", username="owner", permissions=[])
    with patch("src.api.deps._load_user_payload", AsyncMock(return_value=owner)) as load:
        with pytest.raises(GoalRunAdmissionError):
            await arq_worker._validate_standalone_scheduled_admission(payload, "run")
    load.assert_awaited_once_with("owner")
    assert executor._update_session_status.call_args.args[:2] == ("session", TaskStatus.FAILED)
    assert executor._update_session_status.call_args.kwargs["expected_run_id"] == "run"
    release.assert_awaited_once_with("owner", "run", dequeue=True)


async def test_worker_rejects_a_model_removed_from_current_role(queued_schedule):
    from src.kernel.exceptions import AuthorizationError

    payload, executor, release = queued_schedule
    owner = TokenPayload(sub="owner", username="owner", permissions=["chat:write"])
    authorize = AsyncMock(side_effect=AuthorizationError("model_not_allowed"))
    with (
        patch("src.api.deps._load_user_payload", AsyncMock(return_value=owner)),
        patch("src.api.routes.chat.validate_agent_model_access", authorize),
    ):
        with pytest.raises(GoalRunAdmissionError):
            await arq_worker._validate_standalone_scheduled_admission(payload, "run")
    assert authorize.call_args.args[0] == {"model_id": "model"}
    executor._update_session_status.assert_awaited_once()
    release.assert_awaited_once()


async def test_worker_replaces_stale_resolved_model_configuration(queued_schedule):
    payload, executor, release = queued_schedule
    payload["disabled_tools"] = ["delete_file"]
    owner = TokenPayload(sub="owner", username="owner", permissions=["chat:write"])

    async def authorize(options, user):
        assert options == {"model_id": "model"}
        options["_resolved_model_profile"] = {"api_key": "new-key"}

    with (
        patch("src.api.deps._load_user_payload", AsyncMock(return_value=owner)),
        patch("src.api.routes.chat.validate_agent_model_access", authorize),
    ):
        await arq_worker._validate_standalone_scheduled_admission(payload, "run")
    assert payload["agent_options"]["_resolved_model_profile"] == {"api_key": "new-key"}
    assert payload["disabled_tools"] == ["delete_file"]
    executor._update_session_status.assert_not_awaited()
    release.assert_not_awaited()


async def test_worker_keeps_authority_service_outage_retryable(queued_schedule):
    payload, executor, release = queued_schedule
    unavailable = AppError(ErrorCode.SERVICE_UNAVAILABLE)
    with patch("src.api.deps._load_user_payload", AsyncMock(side_effect=unavailable)):
        with pytest.raises(AppError) as failure:
            await arq_worker._validate_standalone_scheduled_admission(payload, "run")
    assert failure.value is unavailable
    executor._update_session_status.assert_not_awaited()
    release.assert_not_awaited()


async def test_local_executor_rechecks_permissions_after_waiting_in_queue(queued_schedule):
    from src.infra.scheduler.runner import execute_standalone_schedule

    owner = TokenPayload(sub="owner", username="owner", permissions=[])
    with (
        patch("src.api.deps._load_user_payload", AsyncMock(return_value=owner)),
        patch("src.api.routes.chat_agent_execution._execute_agent_stream") as execute,
    ):
        with pytest.raises(AppError) as rejected:
            _ = [
                event
                async for event in execute_standalone_schedule(
                    "session", "quick", "check", "owner", agent_options={}
                )
            ]
    assert rejected.value.error_code == ErrorCode.PERMISSION_MISSING
    execute.assert_not_called()


async def test_standalone_executor_refreshes_options_and_preserves_tool_restrictions(
    queued_schedule,
):
    from src.infra.scheduler.runner import execute_standalone_schedule

    owner = TokenPayload(sub="owner", username="owner", permissions=["chat:write"])
    received = {}

    async def authorize(options, user):
        assert "_resolved_model_profile" not in options
        options["_resolved_model_profile"] = {"api_key": "new-key"}

    async def execute(*args, **kwargs):
        received.update(kwargs)
        yield {"event": "message:chunk", "data": {"content": "ok"}}

    with (
        patch("src.api.deps._load_user_payload", AsyncMock(return_value=owner)),
        patch("src.api.routes.chat.validate_agent_model_access", authorize),
        patch("src.api.routes.chat_agent_execution._execute_agent_stream", execute),
    ):
        events = [
            event
            async for event in execute_standalone_schedule(
                "session",
                "quick",
                "check",
                "owner",
                disabled_tools=["delete_file"],
                agent_options={
                    "model_id": "model",
                    "_resolved_model_profile": {"api_key": "old-key"},
                },
            )
        ]
    assert events[0]["event"] == "message:chunk"
    assert received["disabled_tools"] == ["delete_file"]
    assert received["agent_options"]["_resolved_model_profile"] == {"api_key": "new-key"}


def test_scheduled_worker_resolves_the_authorized_executor():
    from src.infra.scheduler.runner import execute_standalone_schedule

    assert arq_worker._resolve_executor("scheduled_agent_stream") is execute_standalone_schedule


async def test_worker_permission_rejection_finalizes_only_its_precreated_trace(queued_schedule):
    from types import MethodType

    from src.infra.task.executor import TaskExecutor

    payload, executor, release = queued_schedule
    payload["trace_id"] = "queued-trace"
    owner = TokenPayload(sub="owner", username="owner", permissions=[])
    writer = SimpleNamespace(
        _flush_redis_buffer=AsyncMock(), flush_mongo_buffer=AsyncMock(), write_event=AsyncMock()
    )
    presenter = SimpleNamespace(
        trace_id="queued-trace",
        complete=AsyncMock(),
        emit=AsyncMock(),
        done=lambda: {"event": "done", "data": {"run_id": "run"}},
        _get_dual_writer=AsyncMock(return_value=writer),
    )
    executor._handle_generic_error = MethodType(TaskExecutor._handle_generic_error, executor)
    executor._send_task_notification = AsyncMock()
    executor._expire_terminal_stream = AsyncMock()
    with (
        patch("src.api.deps._load_user_payload", AsyncMock(return_value=owner)),
        patch("src.infra.writer.present.Presenter", return_value=presenter) as create,
        patch("src.infra.task.executor.get_dual_writer", return_value=writer),
        patch("src.infra.task.executor.emit_undelivered_steer_events", AsyncMock()),
    ):
        with pytest.raises(GoalRunAdmissionError):
            await arq_worker._validate_standalone_scheduled_admission(payload, "run")
    assert create.call_args.args[0].trace_id == "queued-trace"
    assert create.call_args.args[0].run_id == "run"
    presenter.complete.assert_awaited_once_with("error")
    error = writer.write_event.call_args.kwargs
    assert error["trace_id"] == "queued-trace"
    assert error["run_id"] == "run"
    assert error["data"]["code"] == "permission_missing"
    presenter.emit.assert_awaited_once_with(
        {"event": "done", "data": {"run_id": "run", "status": "error"}}
    )
    executor._send_task_notification.assert_awaited_once()
    release.assert_awaited_once_with("owner", "run", dequeue=True)


async def test_worker_releases_rejected_run_slot_if_trace_cleanup_fails(queued_schedule):
    payload, executor, release = queued_schedule
    payload["trace_id"] = "queued-trace"
    owner = TokenPayload(sub="owner", username="owner", permissions=[])
    executor._handle_generic_error.side_effect = RuntimeError("trace storage unavailable")
    with (
        patch("src.api.deps._load_user_payload", AsyncMock(return_value=owner)),
        patch("src.infra.writer.present.Presenter"),
    ):
        with pytest.raises(RuntimeError, match="trace storage unavailable"):
            await arq_worker._validate_standalone_scheduled_admission(payload, "run")
    release.assert_awaited_once_with("owner", "run", dequeue=True)
