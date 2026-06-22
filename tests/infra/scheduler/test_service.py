"""Tests for ScheduledTaskService business logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.extensions import InMemoryPluginSettingsStorage, PluginSettingsService
from src.infra.scheduler import service as service_module
from src.infra.scheduler.service import ScheduledTaskService
from src.kernel.extensions import (
    AGENT_TEAM_PLUGIN_ID,
    PluginManifest,
    PluginRuntime,
    PluginUnavailableError,
    build_agent_team_plugin_manifest,
)
from src.kernel.schemas.scheduled_task import (
    ScheduledTask,
    ScheduledTaskCreate,
    ScheduledTaskStatus,
    ScheduledTaskUpdate,
    TriggerType,
)


def _make_task(**overrides: Any) -> ScheduledTask:
    defaults = dict(
        _id="task_1",
        name="Test Task",
        description=None,
        agent_id="agent_1",
        trigger_type=TriggerType.INTERVAL,
        trigger_config={"seconds": 300},
        input_payload={"message": "hello"},
        status=ScheduledTaskStatus.ACTIVE,
        enabled=True,
        run_on_start=False,
        max_retries=0,
        timeout_seconds=600,
        owner_id="user_1",
        source_session_id=None,
        source_run_id=None,
        created_by="user",
    )
    defaults.update(overrides)
    return ScheduledTask.model_validate(defaults)


def _make_create_request(**overrides: Any) -> ScheduledTaskCreate:
    defaults = dict(
        name="My Task",
        description=None,
        agent_id="agent_1",
        trigger_type=TriggerType.INTERVAL,
        trigger_config={"seconds": 300},
        input_payload={"message": "run report"},
        enabled=True,
        run_on_start=False,
        max_retries=0,
        timeout_seconds=600,
        source_session_id=None,
        source_run_id=None,
        created_by="user",
    )
    defaults.update(overrides)
    return ScheduledTaskCreate.model_validate(defaults)


def _make_update_request(**overrides: Any) -> ScheduledTaskUpdate:
    return ScheduledTaskUpdate.model_validate(overrides)


def test_clear_managed_task_signatures_releases_scheduler_registration_cache() -> None:
    service_module._managed_task_signatures["task_1"] = "signature"

    service_module.clear_managed_task_signatures()

    assert service_module._managed_task_signatures == {}


@pytest.fixture
def service() -> ScheduledTaskService:
    from src.agents import set_plugin_runtime

    service_module._managed_task_signatures.clear()
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    set_plugin_runtime(runtime)
    service = ScheduledTaskService()
    service.plugin_runtime = runtime
    service.plugin_settings_service = PluginSettingsService(
        storage=InMemoryPluginSettingsStorage()
    )
    try:
        yield service
    finally:
        set_plugin_runtime(None)


@pytest.fixture
def mock_scheduler():
    with patch("src.infra.scheduler.service.get_runtime_scheduler") as mock:
        scheduler = MagicMock()
        mock.return_value = scheduler
        scheduler.register_job = MagicMock()
        scheduler.unregister_job = MagicMock()
        scheduler.has_job = MagicMock(return_value=True)
        yield scheduler


@pytest.fixture
def mock_storage():
    with patch("src.infra.scheduler.service.get_scheduled_task_storage") as mock:
        storage = AsyncMock()
        storage.get_active_tasks_marker = AsyncMock(return_value=1)
        mock.return_value = storage
        yield storage


@pytest.fixture
def mock_session_storage():
    with patch("src.infra.scheduler.service.SessionStorage") as mock:
        storage = AsyncMock()
        mock.return_value = storage
        storage.get_unread_counts_for_scheduled_tasks = AsyncMock(return_value={})
        yield storage


@pytest.mark.asyncio
async def test_create_task_persists_and_registers(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    request = _make_create_request()

    mock_storage.create_task = AsyncMock(return_value=None)

    task = await service.create_task(request, owner_id="user_1")

    mock_storage.create_task.assert_called_once()
    mock_scheduler.register_job.assert_called_once()
    assert task.owner_id == "user_1"
    assert task.trigger_type == TriggerType.INTERVAL
    assert task.model_dump(by_alias=True)["_id"] == task.id


@pytest.mark.asyncio
async def test_create_task_syncs_declared_plugin_options_to_settings(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    assert mock_storage is not None
    request = _make_create_request(
        agent_id="team",
        input_payload={
            "message": "team task",
            "plugin_options": {
                "agent_team": {"SELECTED_TEAM_ID": "team-1"},
            },
        },
    )

    task = await service.create_task(request, owner_id="user_1")

    record = await service.plugin_settings_service.storage.get(
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
        scope="scheduled_task",
        subject_id=task.id,
    )
    assert record is not None
    assert record.value == "team-1"
    mock_scheduler.register_job.assert_called_once()


@pytest.mark.asyncio
async def test_create_task_filters_plugin_options_by_scheduled_task_manifest_scope(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    request = _make_create_request(
        agent_id="team",
        input_payload={
            "message": "team task",
            "plugin_options": {
                "agent_team": {
                    "SELECTED_TEAM_ID": "team-1",
                    "UNDECLARED": "drop-me",
                },
                "missing_plugin": {"ANY": "drop-me"},
            },
        },
    )

    task = await service.create_task(request, owner_id="user_1")

    assert task.input_payload == {
        "message": "team task",
        "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-1"}},
    }
    assert await service.plugin_settings_service.storage.get(
        plugin_id="missing_plugin",
        key="ANY",
        scope="scheduled_task",
        subject_id=task.id,
    ) is None
    mock_storage.create_task.assert_called_once()
    mock_scheduler.register_job.assert_called_once()


@pytest.mark.asyncio
async def test_create_task_imports_legacy_payload_keys_from_plugin_manifest(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
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
    service.plugin_runtime = PluginRuntime([manifest])
    request = _make_create_request(
        input_payload={"message": "workflow task", "workflow_id": "workflow-1"},
    )

    task = await service.create_task(request, owner_id="user_1")

    assert task.input_payload == {
        "message": "workflow task",
        "workflow_id": "workflow-1",
        "plugin_options": {
            "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"},
        },
    }
    record = await service.plugin_settings_service.storage.get(
        plugin_id="workflow_runner",
        key="SELECTED_WORKFLOW_ID",
        scope="scheduled_task",
        subject_id=task.id,
    )
    assert record is not None
    assert record.value == "workflow-1"
    mock_scheduler.register_job.assert_called_once()


@pytest.mark.asyncio
async def test_create_cron_task(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    assert mock_storage is not None
    request = _make_create_request(
        name="Weekly Report",
        trigger_type=TriggerType.CRON,
        trigger_config={"day_of_week": "mon", "hour": "9", "minute": "0"},
        input_payload={"message": "weekly report"},
    )

    task = await service.create_task(request, owner_id="user_1")
    assert task.trigger_type == TriggerType.CRON
    mock_scheduler.register_job.assert_called_once()


@pytest.mark.asyncio
async def test_create_cron_task_uses_request_timezone(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    request = _make_create_request(
        name="Morning Report",
        trigger_type=TriggerType.CRON,
        trigger_config={"day_of_week": "mon-fri", "hour": "9", "minute": "0"},
        timezone="Asia/Shanghai",
    )

    task = await service.create_task(request, owner_id="user_1")

    job = mock_scheduler.register_job.call_args.args[0]
    assert task.timezone == "Asia/Shanghai"
    assert str(job.trigger.timezone) == "Asia/Shanghai"


@pytest.mark.asyncio
async def test_create_task_invalid_trigger_raises(
    service: ScheduledTaskService,
) -> None:
    request = _make_create_request(
        name="Bad Task",
        trigger_config={"seconds": -1},  # invalid
        input_payload={},
    )

    with pytest.raises(Exception):
        await service.create_task(request, owner_id="user_1")


@pytest.mark.asyncio
async def test_create_task_rejects_disabled_plugin_owned_agent(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    from src.agents import set_plugin_runtime

    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin(AGENT_TEAM_PLUGIN_ID)
    set_plugin_runtime(runtime)
    request = _make_create_request(agent_id="team")

    try:
        with pytest.raises(PluginUnavailableError) as exc_info:
            await service.create_task(request, owner_id="user_1")
    finally:
        set_plugin_runtime(None)

    assert exc_info.value.plugin_id == AGENT_TEAM_PLUGIN_ID
    mock_storage.create_task.assert_not_called()
    mock_scheduler.register_job.assert_not_called()


@pytest.mark.asyncio
async def test_pause_task_unregisters(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    task = _make_task()
    mock_storage.get_task = AsyncMock(return_value=task)
    mock_storage.update_task = AsyncMock(return_value=True)
    paused_task = _make_task(status=ScheduledTaskStatus.PAUSED, enabled=False)
    mock_storage.get_task = AsyncMock(side_effect=[task, paused_task])

    result = await service.pause_task("task_1")

    assert result == paused_task
    mock_storage.update_task.assert_called_once_with(
        "task_1",
        {"status": ScheduledTaskStatus.PAUSED, "enabled": False},
    )
    mock_scheduler.unregister_job.assert_called_once_with("task_1")


@pytest.mark.asyncio
async def test_resume_task_registers(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    paused = _make_task(status=ScheduledTaskStatus.PAUSED, enabled=False)
    resumed = _make_task(status=ScheduledTaskStatus.ACTIVE, enabled=True)
    mock_storage.get_task = AsyncMock(side_effect=[paused, resumed])
    mock_storage.update_task = AsyncMock(return_value=True)

    result = await service.resume_task("task_1")

    assert result == resumed
    mock_storage.update_task.assert_called_once_with(
        "task_1",
        {"status": ScheduledTaskStatus.ACTIVE, "enabled": True},
    )
    mock_scheduler.register_job.assert_called_once()


@pytest.mark.asyncio
async def test_delete_task_physically_deletes(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    mock_storage.delete_task = AsyncMock(return_value=True)

    deleted = await service.delete_task("task_1")

    assert deleted is True
    mock_scheduler.unregister_job.assert_called_once_with("task_1")
    mock_storage.delete_task.assert_called_once_with("task_1")


@pytest.mark.asyncio
async def test_load_persisted_tasks(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    tasks = [_make_task(_id=f"task_{i}", name=f"Task {i}") for i in range(3)]
    mock_storage.get_active_tasks_marker = AsyncMock(return_value=3)
    mock_storage.list_active_tasks = AsyncMock(return_value=tasks)

    count = await service.load_persisted_tasks()

    assert count == 3
    assert mock_scheduler.register_job.call_count == 3


@pytest.mark.asyncio
async def test_load_persisted_tasks_does_not_honor_run_on_start(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    task = _make_task(run_on_start=True)
    mock_storage.list_active_tasks = AsyncMock(return_value=[task])

    await service.load_persisted_tasks()

    job = mock_scheduler.register_job.call_args.args[0]
    assert job.run_on_start is False


@pytest.mark.asyncio
async def test_register_interval_task_aligns_trigger_to_last_run(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    last_run_at = datetime(2026, 6, 8, 5, 0, tzinfo=timezone.utc)
    task = _make_task(
        trigger_config={"seconds": 300},
        last_run_at=last_run_at,
        created_at=datetime(2026, 6, 8, 4, 0, tzinfo=timezone.utc),
    )
    mock_storage.list_active_tasks = AsyncMock(return_value=[task])

    await service.load_persisted_tasks()

    job = mock_scheduler.register_job.call_args.args[0]
    assert job.trigger.start_date == last_run_at + timedelta(seconds=300)


@pytest.mark.asyncio
async def test_load_persisted_tasks_does_not_reregister_unchanged_tasks(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    task = _make_task()
    mock_storage.list_active_tasks = AsyncMock(return_value=[task])

    await service.load_persisted_tasks()
    await service.load_persisted_tasks()

    assert mock_scheduler.register_job.call_count == 1


@pytest.mark.asyncio
async def test_load_persisted_tasks_skips_full_reload_when_active_marker_unchanged(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    task = _make_task()
    mock_storage.get_active_tasks_marker = AsyncMock(
        side_effect=[
            1,
            1,
        ]
    )
    mock_storage.list_active_tasks = AsyncMock(return_value=[task])

    await service.load_persisted_tasks()
    await service.load_persisted_tasks()

    assert mock_storage.list_active_tasks.call_count == 1
    assert mock_scheduler.register_job.call_count == 1


@pytest.mark.asyncio
async def test_load_persisted_tasks_unregisters_tasks_no_longer_active(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    task = _make_task()
    mock_storage.get_active_tasks_marker = AsyncMock(side_effect=[1, 2])
    mock_storage.list_active_tasks = AsyncMock(side_effect=[[task], []])

    await service.load_persisted_tasks()
    await service.load_persisted_tasks()

    mock_scheduler.unregister_job.assert_called_once_with("task_1")


@pytest.mark.asyncio
async def test_load_persisted_tasks_pauses_expired_date_task(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    task = _make_task(
        trigger_type=TriggerType.DATE,
        trigger_config={"run_date": "2000-01-01T00:00:00+00:00"},
        total_runs=0,
    )
    mock_storage.list_active_tasks = AsyncMock(return_value=[task])
    mock_storage.update_task = AsyncMock(return_value=True)

    count = await service.load_persisted_tasks()

    assert count == 1
    mock_storage.update_task.assert_called_once_with(
        "task_1",
        {"status": ScheduledTaskStatus.PAUSED, "enabled": False},
    )
    mock_scheduler.register_job.assert_not_called()


def test_expired_date_task_interprets_naive_run_date_in_task_timezone() -> None:
    task = _make_task(
        trigger_type=TriggerType.DATE,
        trigger_config={"run_date": "2026-06-13T09:00:00"},
        timezone="Asia/Shanghai",
        total_runs=0,
    )
    now = datetime(2026, 6, 13, 2, 0, tzinfo=timezone.utc)

    assert ScheduledTaskService._is_expired_date_task(task, now=now) is True


@pytest.mark.asyncio
async def test_update_task_refreshes_scheduler(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    original = _make_task()
    updated = _make_task(trigger_config={"seconds": 600})
    mock_storage.get_task = AsyncMock(side_effect=[original, updated])
    mock_storage.update_task = AsyncMock(return_value=True)

    request = _make_update_request(trigger_config={"seconds": 600})
    result = await service.update_task("task_1", request)

    assert result == updated
    mock_storage.update_task.assert_called_once()
    mock_scheduler.register_job.assert_called_once()


@pytest.mark.asyncio
async def test_update_task_syncs_declared_plugin_options_to_settings(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    original = _make_task()
    updated = _make_task(
        input_payload={
            "message": "updated",
            "plugin_options": {
                "agent_team": {"SELECTED_TEAM_ID": "team-2"},
            },
        }
    )
    mock_storage.get_task = AsyncMock(side_effect=[original, updated])
    mock_storage.update_task = AsyncMock(return_value=True)

    result = await service.update_task(
        "task_1",
        _make_update_request(input_payload=updated.input_payload),
    )

    record = await service.plugin_settings_service.storage.get(
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
        scope="scheduled_task",
        subject_id="task_1",
    )
    assert result == updated
    assert record is not None
    assert record.value == "team-2"
    mock_scheduler.register_job.assert_called_once()


@pytest.mark.asyncio
async def test_update_task_filters_plugin_options_by_scheduled_task_manifest_scope(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    original = _make_task()
    sanitized_payload = {
        "message": "updated",
        "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-2"}},
    }
    updated = _make_task(input_payload=sanitized_payload)
    mock_storage.get_task = AsyncMock(side_effect=[original, updated])
    mock_storage.update_task = AsyncMock(return_value=True)

    result = await service.update_task(
        "task_1",
        _make_update_request(
            input_payload={
                "message": "updated",
                "plugin_options": {
                    "agent_team": {
                        "SELECTED_TEAM_ID": "team-2",
                        "UNDECLARED": "drop-me",
                    },
                    "missing_plugin": {"ANY": "drop-me"},
                },
            }
        ),
    )

    assert mock_storage.update_task.call_args.args[1]["input_payload"] == sanitized_payload
    assert result == updated
    assert await service.plugin_settings_service.storage.get(
        plugin_id="missing_plugin",
        key="ANY",
        scope="scheduled_task",
        subject_id="task_1",
    ) is None
    mock_scheduler.register_job.assert_called_once()


@pytest.mark.asyncio
async def test_update_task_can_change_trigger_type(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    original = _make_task(
        trigger_type=TriggerType.INTERVAL,
        trigger_config={"seconds": 300},
    )
    updated = _make_task(
        trigger_type=TriggerType.DATE,
        trigger_config={"run_date": "2099-01-01T12:05:00+00:00"},
        run_on_start=False,
    )
    mock_storage.get_task = AsyncMock(side_effect=[original, updated])
    mock_storage.update_task = AsyncMock(return_value=True)

    request = _make_update_request(
        trigger_type=TriggerType.DATE,
        trigger_config={"run_date": "2099-01-01T12:05:00+00:00"},
        run_on_start=True,
    )
    result = await service.update_task("task_1", request)

    mock_storage.update_task.assert_called_once_with(
        "task_1",
        {
            "trigger_type": TriggerType.DATE,
            "trigger_config": {"run_date": "2099-01-01T12:05:00+00:00"},
            "run_on_start": False,
        },
    )
    mock_scheduler.register_job.assert_called_once()
    assert result == updated


@pytest.mark.asyncio
async def test_update_task_can_clear_description(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    original = _make_task(description="old")
    updated = _make_task(description=None)
    mock_storage.get_task = AsyncMock(side_effect=[original, updated])
    mock_storage.update_task = AsyncMock(return_value=True)

    result = await service.update_task("task_1", _make_update_request(description=None))

    mock_storage.update_task.assert_called_once_with(
        "task_1",
        {"description": None},
    )
    mock_scheduler.register_job.assert_called_once()
    assert result == updated


@pytest.mark.asyncio
async def test_update_task_rejects_disabled_plugin_owned_agent(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    from src.agents import set_plugin_runtime

    original = _make_task(agent_id="fast")
    mock_storage.get_task = AsyncMock(return_value=original)
    mock_storage.update_task = AsyncMock(return_value=True)
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin(AGENT_TEAM_PLUGIN_ID)
    set_plugin_runtime(runtime)

    try:
        with pytest.raises(PluginUnavailableError) as exc_info:
            await service.update_task("task_1", _make_update_request(agent_id="team"))
    finally:
        set_plugin_runtime(None)

    assert exc_info.value.plugin_id == AGENT_TEAM_PLUGIN_ID
    mock_storage.update_task.assert_not_called()
    mock_scheduler.register_job.assert_not_called()


@pytest.mark.asyncio
async def test_to_response() -> None:
    task = _make_task()
    response = ScheduledTaskService.to_response(task)

    assert response.id == "task_1"
    assert response.name == "Test Task"
    assert response.agent_id == "agent_1"
    assert response.trigger_type == TriggerType.INTERVAL
    assert response.owner_id == "user_1"
    assert response.unread_count == 0


@pytest.mark.asyncio
async def test_list_tasks_paginated_returns_unread_counts(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_session_storage: AsyncMock,
) -> None:
    tasks = [
        _make_task(_id="task_1", name="Task 1"),
        _make_task(_id="task_2", name="Task 2"),
    ]
    mock_storage.list_tasks_paginated = AsyncMock(return_value=(tasks, 2))
    mock_session_storage.get_unread_counts_for_scheduled_tasks = AsyncMock(
        return_value={"task_1": 4}
    )

    responses, total = await service.list_tasks_paginated(owner_id="user_1")

    assert total == 2
    assert [response.unread_count for response in responses] == [4, 0]
    mock_session_storage.get_unread_counts_for_scheduled_tasks.assert_called_once_with(
        user_id="user_1",
        scheduled_task_ids=["task_1", "task_2"],
    )


@pytest.mark.asyncio
async def test_list_tasks_paginated_overlays_plugin_settings(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_session_storage: AsyncMock,
) -> None:
    task = _make_task(_id="task_1", input_payload={"message": "hello"})
    mock_storage.list_tasks_paginated = AsyncMock(return_value=([task], 1))
    mock_session_storage.get_unread_counts_for_scheduled_tasks = AsyncMock(return_value={})
    await service.plugin_settings_service.set_setting(
        build_agent_team_plugin_manifest(),
        key="SELECTED_TEAM_ID",
        value="team-from-settings",
        scope="scheduled_task",
        subject_id="task_1",
        updated_by="user_1",
    )

    responses, total = await service.list_tasks_paginated(owner_id="user_1")

    assert total == 1
    assert responses[0].input_payload["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-from-settings"}
    }


@pytest.mark.asyncio
async def test_get_task_response_returns_unread_count(
    service: ScheduledTaskService,
    mock_session_storage: AsyncMock,
) -> None:
    task = _make_task(_id="task_1", owner_id="user_1")
    mock_session_storage.get_unread_counts_for_scheduled_tasks = AsyncMock(
        return_value={"task_1": 7}
    )

    response = await service.get_task_response(task)

    assert response.unread_count == 7


@pytest.mark.asyncio
async def test_get_task_response_overlays_plugin_settings(
    service: ScheduledTaskService,
    mock_session_storage: AsyncMock,
) -> None:
    task = _make_task(_id="task_1", owner_id="user_1", input_payload={})
    mock_session_storage.get_unread_counts_for_scheduled_tasks = AsyncMock(return_value={})
    await service.plugin_settings_service.set_setting(
        build_agent_team_plugin_manifest(),
        key="SELECTED_TEAM_ID",
        value="team-detail",
        scope="scheduled_task",
        subject_id="task_1",
        updated_by="user_1",
    )

    response = await service.get_task_response(task)

    assert response.input_payload["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-detail"}
    }


def test_build_trigger_interval() -> None:
    trigger = ScheduledTaskService._build_trigger(TriggerType.INTERVAL, {"seconds": 300})
    from apscheduler.triggers.interval import IntervalTrigger

    assert isinstance(trigger, IntervalTrigger)


def test_build_trigger_cron() -> None:
    trigger = ScheduledTaskService._build_trigger(TriggerType.CRON, {"hour": "9", "minute": "0"})
    from apscheduler.triggers.cron import CronTrigger

    assert isinstance(trigger, CronTrigger)


def test_build_trigger_date() -> None:
    trigger = ScheduledTaskService._build_trigger(
        TriggerType.DATE,
        {"run_date": "2099-01-01T12:05:00+00:00"},
    )
    from apscheduler.triggers.date import DateTrigger

    assert isinstance(trigger, DateTrigger)
    assert trigger.run_date == datetime(2099, 1, 1, 12, 5, tzinfo=timezone.utc)


def test_build_trigger_date_rejects_past_run_date() -> None:
    with pytest.raises(ValueError, match="future"):
        ScheduledTaskService._build_trigger(
            TriggerType.DATE,
            {"run_date": "2000-01-01T00:00:00+00:00"},
        )


def test_build_trigger_unsupported_raises() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        ScheduledTaskService._build_trigger(cast(Any, "unknown"), {})
