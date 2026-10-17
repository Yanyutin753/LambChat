"""Tests for scheduled task execution status handling."""

from __future__ import annotations

import asyncio
import sys
import types
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.infra.scheduler.runner import ScheduledTaskRunner
from src.infra.task.status import TaskStatus
from src.kernel.schemas.channel import ChannelType
from src.kernel.schemas.scheduled_task import (
    ChannelDeliveryConfig,
    RunStatus,
    ScheduledTask,
    ScheduledTaskStatus,
    TriggerType,
)


def _make_task(**overrides: Any) -> ScheduledTask:
    defaults = dict(
        _id="task_1",
        name="Test Task",
        agent_id="agent_1",
        trigger_type=TriggerType.INTERVAL,
        trigger_config={"seconds": 300},
        input_payload={"message": "hello"},
        status=ScheduledTaskStatus.ACTIVE,
        enabled=True,
        owner_id="user_1",
        timeout_seconds=60,
        max_retries=0,
        created_at=datetime(2026, 6, 8, 5, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return ScheduledTask(**defaults)


@pytest.fixture
def mock_storage():
    with patch("src.infra.scheduler.runner.get_scheduled_task_storage") as mock:
        storage = AsyncMock()
        mock.return_value = storage
        yield storage


@pytest.fixture
def mock_lock():
    with (
        patch(
            "src.infra.scheduler.runner.acquire_task_lock",
            new=AsyncMock(return_value="token"),
        ),
        patch(
            "src.infra.scheduler.runner.acquire_task_slot_lock",
            new=AsyncMock(return_value=True),
        ),
        patch("src.infra.scheduler.runner.release_task_lock", new=AsyncMock()),
    ):
        yield


@pytest.fixture
def mock_spawn_monitor():
    """Replace _spawn_monitor so the detached monitor is collected and awaited inline."""
    spawned: list[asyncio.Task] = []

    def _collect(coro):
        t = asyncio.create_task(coro)
        spawned.append(t)
        return t

    with patch("src.infra.scheduler.runner._spawn_monitor", side_effect=_collect):
        yield spawned


@pytest.fixture(autouse=True)
def mock_default_model():
    """桩掉全局默认模型查询：未选模任务的注入路径不再触达 Mongo/Redis。

    关注注入行为本身的测试会用自己的 monkeypatch 覆盖这里的桩。
    """

    async def _default_model(allowed_models=None):
        return "glm-5.3-flash"

    async def _default_model_id(allowed_models=None):
        return ""

    with (
        patch(
            "src.infra.llm.models_service.get_default_model",
            new=_default_model,
        ),
        patch(
            "src.infra.llm.models_service.get_default_model_id",
            new=_default_model_id,
        ),
    ):
        yield


@pytest.fixture(autouse=True)
def mock_task_authority():
    from src.kernel.schemas.user import TokenPayload

    owner = TokenPayload(sub="user_1", username="owner", permissions=["chat:write"])
    with (
        patch("src.infra.scheduler.runner._resolve_task_owner", AsyncMock(return_value=owner)),
        patch("src.api.routes.chat.validate_agent_model_access", AsyncMock()),
    ):
        yield


async def test_default_scheduled_execution_rejects_revoked_chat_permission():
    from src.kernel.errors import AppError, ErrorCode
    from src.kernel.schemas.user import TokenPayload

    owner = TokenPayload(sub="user_1", username="owner", permissions=[])
    manager = SimpleNamespace(submit=AsyncMock(), submit_arq=AsyncMock())
    with (
        patch("src.infra.scheduler.runner._resolve_task_owner", AsyncMock(return_value=owner)),
        patch("src.infra.task.manager.get_task_manager", return_value=manager),
    ):
        with pytest.raises(AppError) as rejected:
            await ScheduledTaskRunner()._execute_agent(_make_task(), "run", "session")
    assert rejected.value.error_code == ErrorCode.PERMISSION_MISSING
    manager.submit.assert_not_awaited()
    manager.submit_arq.assert_not_awaited()


async def test_default_scheduled_model_is_selected_through_current_role_access(monkeypatch):
    manager = SimpleNamespace(submit=AsyncMock(return_value=("run", "trace")))
    sessions = SimpleNamespace(update_session_metadata=AsyncMock())

    async def authorize(options, user):
        assert options == {}
        assert "chat:write" in user.permissions
        options.update(model="allowed-model", model_id="allowed-id")

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr("src.api.routes.chat.validate_agent_model_access", authorize)
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: manager)
    monkeypatch.setattr("src.infra.session.manager.SessionManager", lambda: sessions)
    monkeypatch.setattr("src.infra.task.concurrency.get_registered_executor", lambda key: object())
    runner = ScheduledTaskRunner()
    runner._wait_for_completion = AsyncMock(return_value={"session_status": "completed"})
    await runner._execute_agent(_make_task(), "run", "session")
    from src.infra.scheduler.runner import execute_standalone_schedule

    assert manager.submit.call_args.kwargs["executor"] is execute_standalone_schedule
    assert manager.submit.call_args.kwargs["agent_options"] == {
        "model": "allowed-model",
        "model_id": "allowed-id",
    }


async def _await_spawned(spawned: list[asyncio.Task]) -> None:
    """Wait for all spawned monitor tasks to complete."""
    if spawned:
        await asyncio.gather(*spawned, return_exceptions=True)


async def test_old_date_run_does_not_unregister_a_reconfigured_schedule(mock_storage):
    task = _make_task(
        trigger_type=TriggerType.DATE, trigger_config={"run_date": "2099-01-01T00:00:00+00:00"}
    )
    mock_storage.pause_completed_date_task = AsyncMock(return_value=False)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(
        return_value={"session_status": "completed", "session_id": "child"}
    )
    with (
        patch("src.infra.scheduler.runner.release_task_lock", AsyncMock()),
        patch("src.infra.scheduler.runner.get_runtime_scheduler") as scheduler,
    ):
        await runner._monitor_and_finalize(
            task=task,
            run_id="run",
            base_session_id="child",
            lock_token="token",
            max_attempts=1,
            trigger_type="date",
            started_at=task.created_at,
        )
    mock_storage.pause_completed_date_task.assert_awaited_once_with(
        task.id, task.trigger_config, task.timezone
    )
    mock_storage.update_task.assert_not_awaited()
    scheduler.return_value.unregister_job.assert_not_called()


async def test_stats_failure_does_not_change_successful_agent_result(mock_storage):
    task = _make_task()
    mock_storage.update_task_run_stats.side_effect = RuntimeError("stats unavailable")
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(
        return_value={"session_status": "completed", "session_id": "child"}
    )
    with patch("src.infra.scheduler.runner.release_task_lock", AsyncMock()):
        await runner._monitor_and_finalize(
            task=task,
            run_id="run",
            base_session_id="child",
            lock_token="token",
            max_attempts=1,
            trigger_type="interval",
            started_at=task.created_at,
        )
    final = mock_storage.update_run.call_args_list[-1].args[1]
    assert final["status"] == RunStatus.SUCCESS
    assert final["finalization_pending"] is True
    mock_storage.complete_run_finalization.assert_not_awaited()
    runner._execute_agent.assert_awaited_once()


async def test_delivery_read_failure_does_not_change_successful_agent_result(mock_storage):
    task = _make_task()
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(
        return_value={"session_status": "completed", "session_id": "child"}
    )
    runner._deliver_success_result = AsyncMock(side_effect=RuntimeError("trace unavailable"))
    with patch("src.infra.scheduler.runner.release_task_lock", AsyncMock()):
        await runner._monitor_and_finalize(
            task=task,
            run_id="run",
            base_session_id="child",
            lock_token="token",
            max_attempts=1,
            trigger_type="interval",
            started_at=task.created_at,
        )
    final = mock_storage.update_run.call_args_list[-1].args[1]
    assert final["status"] == RunStatus.SUCCESS
    assert final["output_result"]["delivery"]["status"] == "failed"
    mock_storage.complete_run_finalization.assert_awaited_once_with("run")


async def test_standalone_finalization_retry_updates_stats_without_running_agent(mock_storage):
    from src.infra.scheduler.runner import reconcile_standalone_finalizations

    record = {
        "_id": "run",
        "task_id": "task",
        "status": "success",
        "trigger_type": "date",
        "scheduled_trigger_config": {"run_date": "2099-01-01T00:00:00+00:00"},
        "scheduled_timezone": "UTC",
        "finalization_pending": True,
    }
    mock_storage.pending_standalone_finalizations.return_value = [record]
    mock_storage.pause_completed_date_task.return_value = True
    with (
        patch.object(ScheduledTaskRunner, "_execute_agent", AsyncMock()) as execute,
        patch("src.infra.scheduler.runner.get_runtime_scheduler") as scheduler,
    ):
        await reconcile_standalone_finalizations()
    execute.assert_not_awaited()
    mock_storage.update_task_run_stats.assert_awaited_once_with("task", "run", RunStatus.SUCCESS)
    mock_storage.pause_completed_date_task.assert_awaited_once_with(
        "task", record["scheduled_trigger_config"], "UTC"
    )
    scheduler.return_value.unregister_job.assert_called_once_with("task")
    mock_storage.complete_run_finalization.assert_awaited_once_with("run")


def test_delayed_cron_peers_share_the_actual_scheduled_fire_slot():
    from datetime import timedelta

    from src.infra.scheduler.runtime import SCHEDULED_FIRE_TIME

    fire_time = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
    task = _make_task(trigger_type=TriggerType.CRON, trigger_config={"minute": "*"})
    token = SCHEDULED_FIRE_TIME.set(fire_time)
    try:
        first = ScheduledTaskRunner._build_schedule_slot(
            task, "cron", fire_time + timedelta(milliseconds=900)
        )
        delayed = ScheduledTaskRunner._build_schedule_slot(
            task, "cron", fire_time + timedelta(seconds=2)
        )
    finally:
        SCHEDULED_FIRE_TIME.reset(token)
    assert first == delayed
    assert first[0] == f"cron:{int(fire_time.timestamp())}"


@pytest.mark.asyncio
async def test_runner_loads_task_with_execution_projection(
    mock_storage: AsyncMock,
    mock_lock: None,
    mock_spawn_monitor: list[asyncio.Task],
) -> None:
    task = _make_task()
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
        return_value={"session_status": "completed", "session_id": "session_1"}
    )

    result = await runner.run("task_1")
    assert result["status"] == "submitted"
    mock_storage.get_task_for_execution.assert_awaited_once_with("task_1")
    mock_storage.get_task.assert_not_awaited()

    # Wait for the detached monitor to finish
    await _await_spawned(mock_spawn_monitor)
    assert mock_storage.update_task_run_stats.await_count == 1


@pytest.mark.asyncio
async def test_runner_lock_ttl_covers_all_attempts(
    mock_storage: AsyncMock,
    mock_spawn_monitor: list[asyncio.Task],
) -> None:
    task = _make_task(timeout_seconds=60, max_retries=2)
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)

    with (
        patch(
            "src.infra.scheduler.runner.acquire_task_lock",
            new=AsyncMock(return_value="token"),
        ) as acquire_lock,
        patch(
            "src.infra.scheduler.runner.acquire_task_slot_lock",
            new=AsyncMock(return_value=True),
        ),
        patch("src.infra.scheduler.runner.release_task_lock", new=AsyncMock()),
    ):
        runner = ScheduledTaskRunner()
        runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
            return_value={"session_status": "completed", "session_id": "session_1"}
        )

        result = await runner.run("task_1")
        assert result["status"] == "submitted"

    acquire_lock.assert_awaited_once()
    assert acquire_lock.call_args.kwargs["ttl"] >= 180
    await _await_spawned(mock_spawn_monitor)


@pytest.mark.asyncio
async def test_runner_skips_when_distributed_schedule_slot_is_claimed(
    mock_storage: AsyncMock,
) -> None:
    task = _make_task()
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock()  # type: ignore[method-assign]

    with (
        patch(
            "src.infra.scheduler.runner.acquire_task_slot_lock",
            new=AsyncMock(return_value=False),
        ) as acquire_slot,
        patch(
            "src.infra.scheduler.runner.acquire_task_lock",
            new=AsyncMock(return_value="token"),
        ) as acquire_lock,
    ):
        result = await runner.run("task_1", trigger_type="interval")

    assert result == {"skipped": True, "reason": "slot_contended"}
    acquire_slot.assert_awaited_once()
    acquire_lock.assert_not_awaited()
    runner._execute_agent.assert_not_awaited()
    mock_storage.create_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_runner_manual_run_bypasses_distributed_schedule_slot(
    mock_storage: AsyncMock,
    mock_spawn_monitor: list[asyncio.Task],
) -> None:
    task = _make_task()
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
        return_value={"session_status": "completed", "session_id": "session_1"}
    )

    with (
        patch(
            "src.infra.scheduler.runner.acquire_task_slot_lock",
            new=AsyncMock(return_value=False),
        ) as acquire_slot,
        patch(
            "src.infra.scheduler.runner.acquire_task_lock",
            new=AsyncMock(return_value="token"),
        ),
        patch("src.infra.scheduler.runner.release_task_lock", new=AsyncMock()),
    ):
        result = await runner.run("task_1", trigger_type="manual")

    assert result["status"] == "submitted"
    acquire_slot.assert_not_awaited()
    await _await_spawned(mock_spawn_monitor)


@pytest.mark.asyncio
async def test_runner_allows_first_run_on_start_before_interval_due(
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    mock_spawn_monitor: list[asyncio.Task],
) -> None:
    now = datetime(2026, 6, 8, 5, 0, tzinfo=timezone.utc)
    task = _make_task(run_on_start=True, total_runs=0, created_at=now)
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    monkeypatch.setattr("src.infra.scheduler.runner.utc_now", lambda: now)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
        return_value={"session_status": "completed", "session_id": "session_1"}
    )

    with (
        patch(
            "src.infra.scheduler.runner.acquire_task_slot_lock",
            new=AsyncMock(return_value=True),
        ) as acquire_slot,
        patch(
            "src.infra.scheduler.runner.acquire_task_lock",
            new=AsyncMock(return_value="token"),
        ),
        patch("src.infra.scheduler.runner.release_task_lock", new=AsyncMock()),
    ):
        result = await runner.run("task_1", trigger_type="interval")

    assert result["status"] == "submitted"
    assert acquire_slot.call_args.args[1].startswith("run_on_start:")
    await _await_spawned(mock_spawn_monitor)


@pytest.mark.asyncio
async def test_runner_records_failed_agent_status_as_failed(
    mock_storage: AsyncMock,
    mock_lock: None,
    mock_spawn_monitor: list[asyncio.Task],
) -> None:
    task = _make_task()
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "session_status": "failed",
            "session_id": "session_1",
            "trace_id": "trace_1",
        }
    )

    result = await runner.run("task_1")
    assert result["status"] == "submitted"

    await _await_spawned(mock_spawn_monitor)
    final_update = mock_storage.update_run.call_args_list[-1].args[1]
    assert final_update["status"] == RunStatus.FAILED
    assert final_update["error_message"] == "Agent run ended with status: failed"
    mock_storage.update_task_run_stats.assert_awaited_once()
    assert mock_storage.update_task_run_stats.call_args.args[2] == RunStatus.FAILED


@pytest.mark.asyncio
async def test_runner_retries_until_success(
    mock_storage: AsyncMock,
    mock_lock: None,
    mock_spawn_monitor: list[asyncio.Task],
) -> None:
    task = _make_task(max_retries=1)
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"session_status": "failed", "session_id": "session_1"},
            {
                "session_status": "completed",
                "session_id": "session_2",
                "trace_id": "trace_2",
            },
        ]
    )

    result = await runner.run("task_1")
    assert result["status"] == "submitted"

    await _await_spawned(mock_spawn_monitor)
    assert runner._execute_agent.call_count == 2
    # 同一 run 的重试必须复用同一锚定时间（issue #212 缓存稳定性）
    anchored_times = [call.kwargs["now"] for call in runner._execute_agent.call_args_list]
    assert anchored_times[0] is not None
    assert anchored_times[1] == anchored_times[0]
    retry_updates = [
        call.args[1]["retry_count"]
        for call in mock_storage.update_run.call_args_list
        if "retry_count" in call.args[1]
    ]
    assert retry_updates == [0, 1]
    final_update = mock_storage.update_run.call_args_list[-1].args[1]
    assert final_update["status"] == RunStatus.SUCCESS


@pytest.mark.asyncio
async def test_runner_sends_success_result_to_configured_channel(
    mock_storage: AsyncMock,
    mock_lock: None,
) -> None:
    task = _make_task(
        delivery=ChannelDeliveryConfig(
            channel_type="feishu",
            chat_id="oc_target",
            channel_instance_id="bot_a",
        )
    )
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "session_status": "completed",
            "session_id": "session_1",
            "trace_id": "trace_1",
        }
    )

    trace_storage = AsyncMock()
    trace_storage.get_run_events = AsyncMock(
        return_value=[
            {"event_type": "user:message", "data": {"content": "Generate report"}},
            {"event_type": "message", "data": {"role": "assistant", "content": "Report ready"}},
        ]
    )
    coordinator = AsyncMock()
    coordinator.send_message = AsyncMock(return_value=True)

    spawned: list[asyncio.Task] = []

    def _collect(coro):
        t = asyncio.create_task(coro)
        spawned.append(t)
        return t

    with (
        patch("src.infra.scheduler.runner.get_trace_storage", return_value=trace_storage),
        patch("src.infra.scheduler.runner.get_channel_coordinator", return_value=coordinator),
        patch("src.infra.scheduler.runner._spawn_monitor", side_effect=_collect),
    ):
        result = await runner.run("task_1")

    assert result["status"] == "submitted"

    # Re-enter patches while the monitor tasks execute
    with (
        patch("src.infra.scheduler.runner.get_trace_storage", return_value=trace_storage),
        patch("src.infra.scheduler.runner.get_channel_coordinator", return_value=coordinator),
    ):
        await _await_spawned(spawned)

    trace_storage.get_run_events.assert_awaited_once()
    assert trace_storage.get_run_events.call_args.args[0] == "session_1"
    sent_run_id = trace_storage.get_run_events.call_args.args[1]
    assert isinstance(sent_run_id, str)
    coordinator.send_message.assert_awaited_once_with(
        "user_1",
        ChannelType.FEISHU,
        "oc_target",
        "Report ready",
        instance_id="bot_a",
    )
    final_update = mock_storage.update_run.call_args_list[-1].args[1]
    assert final_update["status"] == RunStatus.SUCCESS
    assert final_update["output_result"]["delivery"] == {
        "status": "sent",
        "channel_type": "feishu",
        "chat_id": "oc_target",
        "channel_instance_id": "bot_a",
    }


def test_extract_channel_delivery_text_uses_assistant_chunks_only() -> None:
    events = [
        {"event_type": "message", "data": {"role": "user", "content": "Do not send me"}},
        {"event_type": "message:chunk", "data": {"content": "Hello "}},
        {"event_type": "message:chunk", "data": {"content": "world"}},
    ]

    text = ScheduledTaskRunner._extract_channel_delivery_text(events, max_content_chars=100)

    assert text == "Hello world"


@pytest.mark.asyncio
async def test_runner_does_not_retry_timeout(
    mock_storage: AsyncMock,
    mock_lock: None,
    mock_spawn_monitor: list[asyncio.Task],
) -> None:
    task = _make_task(max_retries=1)
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
        return_value={"session_status": "timeout", "session_id": "session_1"}
    )

    result = await runner.run("task_1")
    assert result["status"] == "submitted"

    await _await_spawned(mock_spawn_monitor)
    assert runner._execute_agent.call_count == 1
    final_update = mock_storage.update_run.call_args_list[-1].args[1]
    assert final_update["status"] == RunStatus.TIMEOUT


@pytest.mark.asyncio
async def test_wait_for_completion_waits_until_terminal_without_cancelling_run() -> None:
    manager = AsyncMock()
    manager.get_run_status = AsyncMock(side_effect=[TaskStatus.RUNNING, TaskStatus.COMPLETED])
    runner = ScheduledTaskRunner()
    with patch("src.infra.scheduler.runner.asyncio.sleep", AsyncMock()):
        result = await runner._wait_for_completion(manager, "session_1", "run_1", "user_1")
    assert result == {"session_status": "completed"}
    manager.cancel_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_agent_hides_injected_timestamp_from_display(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _make_task(
        input_payload={
            "message": "Summarize the latest AI news",
            "user_timezone": "Asia/Shanghai",
        }
    )
    submitted: dict[str, Any] = {}

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            submitted.update(kwargs)
            return "run_1", "trace_1"

        async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
            assert session_id == "session_1"
            assert run_id == "run_1"
            return TaskStatus.COMPLETED

    class _FakeSessionManager:
        def __init__(self) -> None:
            self.metadata: dict[str, Any] | None = None

        async def update_session_metadata(
            self,
            session_id: str,
            metadata: dict[str, Any],
        ) -> None:
            assert session_id == "session_1"
            self.metadata = metadata

    session_manager = _FakeSessionManager()

    monkeypatch.setattr(
        "src.infra.task.manager.get_task_manager",
        lambda: _FakeTaskManager(),
    )
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor",
        lambda key: (lambda *args, **kwargs: None) if key == "agent_stream" else None,
    )
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: session_manager,
    )

    result = await ScheduledTaskRunner()._execute_agent(
        task,
        run_id="run_1",
        session_id="session_1",
    )

    assert result == {
        "session_status": "completed",
        "session_id": "session_1",
        "trace_id": "trace_1",
    }
    assert submitted["message"].startswith("[User message sent at: ")
    assert " +08:00 Asia/Shanghai] Summarize the latest AI news" in submitted["message"]
    assert submitted["display_message"] == "Summarize the latest AI news"
    assert submitted["recommendation_input"] == "Summarize the latest AI news"
    assert "[User message sent at:" not in submitted["display_message"]
    assert "[User message sent at:" not in submitted["recommendation_input"]
    assert submitted["write_user_message_immediately"] is True
    assert submitted["session_metadata"] == {
        "source": "scheduled_task",
        "scheduled_task_id": "task_1",
        "executor_key": "scheduled_agent_stream",
        "scheduled_task_run_id": "run_1",
        "scheduled_task_trigger_type": "interval",
        "hidden_from_conversation_list": True,
    }
    assert session_manager.metadata == {
        "source": "scheduled_task",
        "scheduled_task_id": "task_1",
        "executor_key": "scheduled_agent_stream",
        "scheduled_task_run_id": "run_1",
        "scheduled_task_trigger_type": "interval",
        "hidden_from_conversation_list": True,
    }


@pytest.mark.asyncio
async def test_execute_agent_runs_scheduled_tasks_in_auto_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _make_task(input_payload={"message": "Run the report"})
    submitted: dict[str, Any] = {}

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            submitted.update(kwargs)
            return "run_1", "trace_1"

        async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
            return TaskStatus.COMPLETED

    class _FakeSessionManager:
        async def update_session_metadata(
            self,
            session_id: str,
            metadata: dict[str, Any],
        ) -> None:
            return None

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeTaskManager())
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor",
        lambda key: (lambda *args, **kwargs: None) if key == "agent_stream" else None,
    )
    monkeypatch.setattr("src.infra.session.manager.SessionManager", lambda: _FakeSessionManager())

    await ScheduledTaskRunner()._execute_agent(task, run_id="run_1", session_id="session_1")

    assert submitted["auto_mode"] is True


@pytest.mark.asyncio
async def test_execute_agent_forwards_attachments_to_local_submit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attachments = [
        {
            "id": "att-1",
            "key": "attachments/user-1/report.pdf",
            "name": "report.pdf",
            "type": "document",
            "mime_type": "application/pdf",
            "size": 12345,
            "url": "/api/upload/file/attachments/user-1/report.pdf",
        }
    ]
    task = _make_task(
        input_payload={
            "message": "Summarize the report",
            "attachments": attachments,
        }
    )
    submitted: dict[str, Any] = {}

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            submitted.update(kwargs)
            return "run_1", "trace_1"

        async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
            return TaskStatus.COMPLETED

    class _FakeSessionManager:
        async def update_session_metadata(
            self,
            session_id: str,
            metadata: dict[str, Any],
        ) -> None:
            return None

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeTaskManager())
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor",
        lambda key: (lambda *args, **kwargs: None) if key == "agent_stream" else None,
    )
    monkeypatch.setattr("src.infra.session.manager.SessionManager", lambda: _FakeSessionManager())

    await ScheduledTaskRunner()._execute_agent(task, run_id="run_1", session_id="session_1")

    assert submitted["attachments"] == attachments


@pytest.mark.asyncio
async def test_execute_agent_resolves_persona_id_for_non_team_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _make_task(
        agent_id="fast",
        input_payload={
            "message": "Write the brief",
            "persona_preset_id": "persona-1",
        },
    )
    submitted: dict[str, Any] = {}

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            submitted.update(kwargs)
            return "run_1", "trace_1"

        async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
            return TaskStatus.COMPLETED

    class _FakeSessionManager:
        async def update_session_metadata(
            self,
            session_id: str,
            metadata: dict[str, Any],
        ) -> None:
            submitted["updated_metadata"] = metadata

    async def _fake_resolve_persona_request(request: Any, user: Any) -> None:
        assert request.persona_preset_id == "persona-1"
        assert user.sub == "user_1"
        request.persona_system_prompt = "You are the writer."
        request.enabled_skills = ["writing"]

    fake_manager_module = types.ModuleType("src.infra.task.manager")
    fake_manager_module.get_task_manager = lambda: _FakeTaskManager()
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setitem(sys.modules, "src.infra.task.manager", fake_manager_module)
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor",
        lambda key: (lambda *args, **kwargs: None) if key == "agent_stream" else None,
    )
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: _FakeSessionManager(),
    )
    monkeypatch.setattr(
        "src.infra.scheduler.runner._resolve_task_owner",
        AsyncMock(
            return_value=type("User", (), {"sub": "user_1", "permissions": ["chat:write"]})()
        ),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.resolve_persona_request",
        _fake_resolve_persona_request,
    )

    await ScheduledTaskRunner()._execute_agent(
        task,
        run_id="run_1",
        session_id="session_1",
    )

    assert submitted["persona_system_prompt"] == "You are the writer."
    assert submitted["enabled_skills"] == ["writing"]
    assert submitted["team_id"] is None
    assert submitted["session_metadata"]["persona_preset_id"] == "persona-1"
    assert submitted["session_metadata"]["scheduled_task_trigger_type"] == "interval"
    assert submitted["updated_metadata"]["persona_preset_id"] == "persona-1"
    assert task.input_payload == {
        "message": "Write the brief",
        "persona_preset_id": "persona-1",
    }


@pytest.mark.asyncio
async def test_execute_agent_passes_team_id_for_team_agent_without_persona(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _make_task(
        agent_id="team",
        input_payload={
            "message": "Plan the launch",
            "team_id": "team-1",
            "persona_preset_id": "persona-ignored",
        },
    )
    submitted: dict[str, Any] = {}

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            submitted.update(kwargs)
            return "run_1", "trace_1"

        async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
            return TaskStatus.COMPLETED

    class _FakeSessionManager:
        async def update_session_metadata(
            self,
            session_id: str,
            metadata: dict[str, Any],
        ) -> None:
            submitted["updated_metadata"] = metadata

    async def _unexpected_resolve_persona_request(request: Any, user: Any) -> None:
        raise AssertionError("team scheduled tasks should not resolve persona presets")

    fake_manager_module = types.ModuleType("src.infra.task.manager")
    fake_manager_module.get_task_manager = lambda: _FakeTaskManager()
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setitem(sys.modules, "src.infra.task.manager", fake_manager_module)
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor",
        lambda key: (lambda *args, **kwargs: None) if key == "agent_stream" else None,
    )
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: _FakeSessionManager(),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.resolve_persona_request",
        _unexpected_resolve_persona_request,
    )

    await ScheduledTaskRunner()._execute_agent(
        task,
        run_id="run_1",
        session_id="session_1",
    )

    assert submitted["team_id"] == "team-1"
    assert submitted["persona_system_prompt"] is None
    assert submitted["enabled_skills"] is None
    assert submitted["session_metadata"]["team_id"] == "team-1"
    assert submitted["session_metadata"]["scheduled_task_trigger_type"] == "interval"
    assert "persona_preset_id" not in submitted["session_metadata"]
    assert submitted["updated_metadata"]["team_id"] == "team-1"


@pytest.mark.asyncio
async def test_execute_agent_uses_arq_backend_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attachments = [
        {
            "id": "att-1",
            "key": "attachments/user-1/report.pdf",
            "name": "report.pdf",
            "type": "document",
            "mime_type": "application/pdf",
            "size": 12345,
            "url": "/api/upload/file/attachments/user-1/report.pdf",
        }
    ]
    task = _make_task(
        input_payload={
            "message": "Run distributed report",
            "attachments": attachments,
        }
    )
    submitted: dict[str, Any] = {}

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            raise AssertionError("scheduled task should not use local submit with arq")

        async def submit_arq(self, **kwargs: Any) -> tuple[str, str]:
            submitted.update(kwargs)
            return "run_1", "trace_1"

        async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
            assert session_id == "session_1"
            assert run_id == "run_1"
            return TaskStatus.COMPLETED

    class _FakeSessionManager:
        async def update_session_metadata(
            self,
            session_id: str,
            metadata: dict[str, Any],
        ) -> None:
            assert session_id == "session_1"
            assert metadata["source"] == "scheduled_task"

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "arq")
    monkeypatch.setattr(
        "src.infra.task.manager.get_task_manager",
        lambda: _FakeTaskManager(),
    )
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor",
        lambda key: (lambda *args, **kwargs: None) if key == "agent_stream" else None,
    )
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: _FakeSessionManager(),
    )

    result = await ScheduledTaskRunner()._execute_agent(
        task,
        run_id="run_1",
        session_id="session_1",
    )

    assert result == {
        "session_status": "completed",
        "session_id": "session_1",
        "trace_id": "trace_1",
    }
    assert submitted["executor_key"] == "scheduled_agent_stream"
    assert submitted["dispatch_id"] == "scheduled:run_1:session_1"
    assert submitted["run_id"] == "run_1"
    assert submitted["session_id"] == "session_1"
    assert submitted["display_message"] == "Run distributed report"
    assert submitted["attachments"] == attachments
    assert submitted["session_metadata"] == {
        "source": "scheduled_task",
        "scheduled_task_id": "task_1",
        "executor_key": "scheduled_agent_stream",
        "scheduled_task_run_id": "run_1",
        "scheduled_task_trigger_type": "interval",
        "hidden_from_conversation_list": True,
    }
    assert submitted["write_user_message_immediately"] is True


@pytest.mark.asyncio
async def test_execute_agent_anchors_timestamp_to_run_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一 run 的重试必须复用首次执行的时间戳（issue #212 缓存稳定性）。"""
    task = _make_task(input_payload={"message": "hello", "user_timezone": "Asia/Shanghai"})
    submitted: dict[str, Any] = {}

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            submitted.update(kwargs)
            return "run_1", "trace_1"

        async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
            return TaskStatus.COMPLETED

    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeTaskManager())
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor",
        lambda key: (lambda *args, **kwargs: None) if key == "agent_stream" else None,
    )

    class _FakeSessionManager:
        async def update_session_metadata(self, session_id: str, metadata: dict) -> None:
            pass

    monkeypatch.setattr("src.infra.session.manager.SessionManager", lambda: _FakeSessionManager())

    anchored = datetime(2026, 8, 22, 1, 2, 3, tzinfo=timezone.utc)
    await ScheduledTaskRunner()._execute_agent(
        task, run_id="run_1", session_id="session_1", now=anchored
    )
    assert "Do not guess" in submitted["message"]
    assert submitted["message"].startswith(
        "[User message sent at: 2026-08-22 09:02:03 +08:00 Asia/Shanghai] "
    )


@pytest.mark.asyncio
async def test_execute_agent_injects_default_model_when_task_has_no_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未显式选模的定时任务提交前注入全局默认模型。

    不注入时节点运行期静默走默认模型，但 presenter/token:usage 都拿不到
    模型名——用量面板的模型列和费用全部缺失（回归：定时任务记录 model "-"）。
    """
    task = _make_task(input_payload={"message": "Run the report"})
    submitted: dict[str, Any] = {}

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            submitted.update(kwargs)
            return "run_1", "trace_1"

        async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
            return TaskStatus.COMPLETED

    class _FakeSessionManager:
        async def update_session_metadata(
            self,
            session_id: str,
            metadata: dict[str, Any],
        ) -> None:
            return None

    async def _default_model(allowed_models=None):
        return "glm-5.3-flash"

    async def _default_model_id(allowed_models=None):
        return "479d617d-8105-49e0-8401-1dbdf2fe5358"

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeTaskManager())
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor",
        lambda key: (lambda *args, **kwargs: None) if key == "agent_stream" else None,
    )
    monkeypatch.setattr("src.infra.session.manager.SessionManager", lambda: _FakeSessionManager())
    monkeypatch.setattr("src.infra.llm.models_service.get_default_model", _default_model)
    monkeypatch.setattr("src.infra.llm.models_service.get_default_model_id", _default_model_id)

    await ScheduledTaskRunner()._execute_agent(task, run_id="run_1", session_id="session_1")

    assert submitted["agent_options"] == {
        "model": "glm-5.3-flash",
        "model_id": "479d617d-8105-49e0-8401-1dbdf2fe5358",
    }


@pytest.mark.asyncio
async def test_execute_agent_keeps_existing_model_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """任务已带模型时不得覆盖用户/Agent 创建时的显式选择。"""
    task = _make_task(
        input_payload={
            "message": "Run the report",
            "agent_options": {"model": "deepseek-flash", "response_language": "zh"},
        }
    )
    submitted: dict[str, Any] = {}

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            submitted.update(kwargs)
            return "run_1", "trace_1"

        async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
            return TaskStatus.COMPLETED

    class _FakeSessionManager:
        async def update_session_metadata(
            self,
            session_id: str,
            metadata: dict[str, Any],
        ) -> None:
            return None

    async def _default_model(allowed_models=None):
        return "glm-5.3-flash"

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeTaskManager())
    monkeypatch.setattr(
        "src.infra.task.concurrency.get_registered_executor",
        lambda key: (lambda *args, **kwargs: None) if key == "agent_stream" else None,
    )
    monkeypatch.setattr("src.infra.session.manager.SessionManager", lambda: _FakeSessionManager())
    monkeypatch.setattr("src.infra.llm.models_service.get_default_model", _default_model)
    # 显式选模走 validate_agent_model_access 分支，需要任务 owner 在场
    monkeypatch.setattr(
        "src.infra.scheduler.runner._resolve_task_owner",
        AsyncMock(return_value=SimpleNamespace(sub="user_1", permissions=["chat:write"])),
    )
    monkeypatch.setattr("src.api.routes.chat.validate_agent_model_access", AsyncMock())

    await ScheduledTaskRunner()._execute_agent(task, run_id="run_1", session_id="session_1")

    assert submitted["agent_options"] == {
        "model": "deepseek-flash",
        "response_language": "zh",
    }


@pytest.mark.parametrize("elapsed", [60, 120, 180, 600])
def test_interval_slots_keep_every_minute_despite_completion_latency(elapsed):
    from datetime import timedelta

    anchor = datetime(2026, 10, 16, 17, 36, 41, 886000, tzinfo=timezone.utc)
    now = anchor + timedelta(seconds=elapsed)
    task = _make_task(
        created_at=anchor,
        trigger_config={"seconds": 60},
        last_run_at=now - timedelta(seconds=50),
        total_runs=1,
        run_on_start=True,
    )
    slot = ScheduledTaskRunner._build_schedule_slot(task, "interval", now)
    assert slot[2] == now
    # Delayed peers must dedupe the same fixed slot even after completion stats change.
    task.last_run_at = now + timedelta(seconds=5)
    assert (
        ScheduledTaskRunner._build_schedule_slot(task, "interval", now + timedelta(seconds=10))
        == slot
    )


def test_interval_slot_advances_while_first_run_is_still_open():
    from datetime import timedelta

    anchor = datetime(2026, 10, 16, 17, 36, 41, tzinfo=timezone.utc)
    task = _make_task(
        created_at=anchor, trigger_config={"seconds": 60}, total_runs=0, run_on_start=True
    )
    first = ScheduledTaskRunner._build_schedule_slot(task, "interval", anchor)
    next_slot = ScheduledTaskRunner._build_schedule_slot(
        task, "interval", anchor + timedelta(seconds=60)
    )
    assert first[0].startswith("run_on_start:")
    assert next_slot[0] != first[0]
    assert next_slot[2] == anchor + timedelta(seconds=60)


def test_interval_slot_is_not_due_before_first_fixed_tick():
    from datetime import timedelta

    anchor = datetime(2026, 10, 16, 17, 36, 41, tzinfo=timezone.utc)
    task = _make_task(created_at=anchor, trigger_config={"seconds": 60})
    slot = ScheduledTaskRunner._build_schedule_slot(
        task, "interval", anchor + timedelta(seconds=59)
    )
    assert slot[2] == anchor + timedelta(seconds=60)


def test_legacy_interval_without_creation_time_remains_runnable():
    now = datetime(2026, 10, 16, 17, 37, 41, tzinfo=timezone.utc)
    task = _make_task(created_at=None, trigger_config={"seconds": 60})
    slot = ScheduledTaskRunner._build_schedule_slot(task, "interval", now)
    assert slot[2] is None
