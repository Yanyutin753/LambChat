"""Tests for scheduled task execution status handling."""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
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
from src.kernel.extensions import (
    PluginManifest,
    PluginRuntime,
    PluginUnavailableError,
    build_agent_team_plugin_manifest,
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


@pytest.mark.asyncio
async def test_runner_loads_task_with_execution_projection(
    mock_storage: AsyncMock,
    mock_lock: None,
) -> None:
    task = _make_task()
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
        return_value={"session_status": "completed", "session_id": "session_1"}
    )

    result = await runner.run("task_1")

    assert result["status"] == RunStatus.SUCCESS.value
    mock_storage.get_task_for_execution.assert_awaited_once_with("task_1")
    mock_storage.get_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_runner_lock_ttl_covers_all_attempts(
    mock_storage: AsyncMock,
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

        await runner.run("task_1")

    acquire_lock.assert_awaited_once()
    assert acquire_lock.call_args.kwargs["ttl"] >= 180


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

    assert result["status"] == RunStatus.SUCCESS.value
    acquire_slot.assert_not_awaited()


@pytest.mark.asyncio
async def test_runner_allows_first_run_on_start_before_interval_due(
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
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

    assert result["status"] == RunStatus.SUCCESS.value
    assert acquire_slot.call_args.args[1].startswith("run_on_start:")


@pytest.mark.asyncio
async def test_runner_records_failed_agent_status_as_failed(
    mock_storage: AsyncMock,
    mock_lock: None,
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

    assert result["status"] == RunStatus.FAILED.value
    final_update = mock_storage.update_run.call_args_list[-1].args[1]
    assert final_update["status"] == RunStatus.FAILED
    assert final_update["error_message"] == "Agent run ended with status: failed"
    mock_storage.update_task_run_stats.assert_awaited_once()
    assert mock_storage.update_task_run_stats.call_args.args[2] == RunStatus.FAILED


@pytest.mark.asyncio
async def test_runner_retries_until_success(
    mock_storage: AsyncMock,
    mock_lock: None,
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

    assert result["status"] == RunStatus.SUCCESS.value
    assert runner._execute_agent.call_count == 2
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

    with (
        patch("src.infra.scheduler.runner.get_trace_storage", return_value=trace_storage),
        patch("src.infra.scheduler.runner.get_channel_coordinator", return_value=coordinator),
    ):
        result = await runner.run("task_1")

    assert result["status"] == RunStatus.SUCCESS.value
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
) -> None:
    task = _make_task(max_retries=1)
    mock_storage.get_task_for_execution = AsyncMock(return_value=task)
    runner = ScheduledTaskRunner()
    runner._execute_agent = AsyncMock(  # type: ignore[method-assign]
        return_value={"session_status": "timeout", "session_id": "session_1"}
    )

    result = await runner.run("task_1")

    assert result["status"] == RunStatus.TIMEOUT.value
    assert runner._execute_agent.call_count == 1
    final_update = mock_storage.update_run.call_args_list[-1].args[1]
    assert final_update["status"] == RunStatus.TIMEOUT


@pytest.mark.asyncio
async def test_wait_for_completion_times_out_and_cancels_run() -> None:
    manager = AsyncMock()
    manager.get_run_status = AsyncMock(return_value=TaskStatus.RUNNING)
    manager.cancel_run = AsyncMock(return_value={"success": True})
    runner = ScheduledTaskRunner()

    result = await runner._wait_for_completion(
        manager,
        session_id="session_1",
        run_id="run_1",
        user_id="user_1",
        timeout_seconds=0,
    )

    assert result == {"session_status": "timeout"}
    manager.cancel_run.assert_awaited_once_with("run_1", user_id="user_1")


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
        "scheduled_task_run_id": "run_1",
        "hidden_from_conversation_list": True,
    }
    assert session_manager.metadata == {
        "source": "scheduled_task",
        "scheduled_task_id": "task_1",
        "scheduled_task_run_id": "run_1",
        "hidden_from_conversation_list": True,
    }


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
        AsyncMock(return_value=type("User", (), {"sub": "user_1", "permissions": []})()),
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
    assert submitted["updated_metadata"]["persona_preset_id"] == "persona-1"
    assert task.input_payload == {
        "message": "Write the brief",
        "persona_preset_id": "persona-1",
    }


@pytest.mark.asyncio
async def test_execute_agent_passes_team_id_for_team_agent_without_persona(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import set_plugin_runtime

    set_plugin_runtime(PluginRuntime([build_agent_team_plugin_manifest()]))
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
    assert "team_id" not in submitted["session_metadata"]
    assert submitted["session_metadata"]["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }
    assert "persona_preset_id" not in submitted["session_metadata"]
    assert "team_id" not in submitted["updated_metadata"]
    assert submitted["updated_metadata"]["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }


@pytest.mark.asyncio
async def test_execute_agent_prefers_plugin_option_team_id_for_team_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import set_plugin_runtime

    set_plugin_runtime(PluginRuntime([build_agent_team_plugin_manifest()]))
    task = _make_task(
        agent_id="team",
        input_payload={
            "message": "Plan the launch",
            "team_id": "legacy-team",
            "plugin_options": {
                "agent_team": {"SELECTED_TEAM_ID": "plugin-team"}
            },
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

    try:
        await ScheduledTaskRunner()._execute_agent(
            task,
            run_id="run_1",
            session_id="session_1",
        )
    finally:
        set_plugin_runtime(None)

    assert submitted["team_id"] == "plugin-team"
    assert "team_id" not in submitted["session_metadata"]
    assert submitted["session_metadata"]["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "plugin-team"}
    }


@pytest.mark.asyncio
async def test_execute_agent_carries_generic_scheduled_task_plugin_options_to_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        permissions=["workflow_runner:read"],
        settings=[
            {
                "key": "SELECTED_WORKFLOW_ID",
                "type": "string",
                "scope": "scheduled_task",
            }
        ],
        frontend={
            "scheduled_task_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                    "legacy_payload_keys": ["workflow_id"],
                }
            ]
        },
    )
    task = _make_task(
        agent_id="fast",
        input_payload={"message": "Run workflow", "workflow_id": "workflow-1"},
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
    runner = ScheduledTaskRunner()
    runner.set_plugin_runtime(PluginRuntime([manifest]))

    await runner._execute_agent(task, run_id="run_1", session_id="session_1")

    assert submitted["team_id"] is None
    assert submitted["session_metadata"]["plugin_options"] == {
        "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"}
    }
    assert submitted["updated_metadata"]["plugin_options"] == {
        "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"}
    }


@pytest.mark.asyncio
async def test_execute_agent_rejects_disabled_plugin_owned_team_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import set_plugin_runtime

    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")
    set_plugin_runtime(runtime)
    task = _make_task(
        agent_id="team",
        input_payload={"message": "Plan the launch", "team_id": "team-1"},
    )

    class _FakeTaskManager:
        async def submit(self, **kwargs: Any) -> tuple[str, str]:
            raise AssertionError("disabled plugin-owned agent should not be submitted")

    class _FakeSessionManager:
        async def update_session_metadata(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("disabled plugin-owned agent should not write metadata")

    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: _FakeTaskManager())
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: _FakeSessionManager(),
    )

    try:
        with pytest.raises(PluginUnavailableError) as exc_info:
            await ScheduledTaskRunner()._execute_agent(
                task,
                run_id="run_1",
                session_id="session_1",
            )
        assert "agent_team" in str(exc_info.value)
    finally:
        set_plugin_runtime(None)


@pytest.mark.asyncio
async def test_execute_agent_uses_arq_backend_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _make_task(input_payload={"message": "Run distributed report"})
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
    assert submitted["executor_key"] == "agent_stream"
    assert submitted["run_id"] == "run_1"
    assert submitted["session_id"] == "session_1"
    assert submitted["display_message"] == "Run distributed report"
    assert submitted["session_metadata"] == {
        "source": "scheduled_task",
        "scheduled_task_id": "task_1",
        "scheduled_task_run_id": "run_1",
        "hidden_from_conversation_list": True,
    }
    assert submitted["write_user_message_immediately"] is True
