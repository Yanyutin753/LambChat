"""Tests for ScheduledTaskService business logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.infra.scheduler import service as service_module
from src.infra.scheduler.service import ScheduledTaskService
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
    service_module._managed_task_signatures.clear()
    return ScheduledTaskService()


@pytest.fixture(autouse=True)
def mock_attachment_mutation_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _acquire(_task_id: str) -> str:
        return "mutation-token"

    async def _release(_task_id: str, _token: str) -> None:
        return None

    monkeypatch.setattr(
        service_module,
        "acquire_attachment_mutation_lock",
        _acquire,
        raising=False,
    )
    monkeypatch.setattr(
        service_module,
        "release_attachment_mutation_lock",
        _release,
        raising=False,
    )


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
async def test_create_task_claims_definition_attachments_before_registration(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    persisted: ScheduledTask | None = None

    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> list[str]:
            assert keys == ["key-a"]
            assert uploaded_by == "user_1"
            assert task_id
            events.append("claim")
            return keys

    async def _create_task(task: ScheduledTask) -> ScheduledTask:
        nonlocal persisted
        persisted = task
        events.append("persist_pending")
        return task

    async def _commit_attachment_update(
        task_id: str,
        updates: dict[str, Any],
        attachment_keys: list[str],
    ) -> ScheduledTask:
        assert persisted is not None
        assert task_id == persisted.id
        assert updates == {"enabled": True}
        assert attachment_keys == ["key-a"]
        events.append("commit_active")
        return persisted.model_copy(
            update={
                "enabled": True,
                "attachment_keys": ["key-a"],
                "pending_attachment_claim_keys": [],
                "attachment_setup_pending": False,
            }
        )

    mock_storage.create_task.side_effect = _create_task
    mock_storage.commit_attachment_update.side_effect = _commit_attachment_update
    mock_scheduler.register_job.side_effect = lambda _job: events.append("register")
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords(), raising=False)
    request = _make_create_request(
        input_payload={
            "message": "run later",
            "attachments": [{"key": "key-a"}, {"key": "key-a"}],
        }
    )

    task = await service.create_task(request, owner_id="user_1")

    assert persisted is not None
    assert persisted.enabled is False
    assert persisted.attachment_setup_pending is True
    assert persisted.pending_attachment_claim_keys == ["key-a"]
    assert task.attachment_keys == ["key-a"]
    assert events == ["persist_pending", "claim", "commit_active", "register"]


@pytest.mark.asyncio
async def test_create_task_claim_failure_removes_non_runnable_definition(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> list[str]:
            raise service_module.AttachmentClaimError()

    mock_storage.create_task = AsyncMock()
    mock_storage.delete_task = AsyncMock(return_value=True)
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords(), raising=False)
    request = _make_create_request(
        input_payload={"attachments": [{"key": "key-a"}]},
    )

    with pytest.raises(service_module.AttachmentClaimError):
        await service.create_task(request, owner_id="user_1")

    created_task = mock_storage.create_task.await_args.args[0]
    assert created_task.enabled is False
    assert created_task.attachment_setup_pending is True
    mock_storage.delete_task.assert_awaited_once_with(created_task.id)
    mock_scheduler.register_job.assert_not_called()


@pytest.mark.asyncio
async def test_create_task_commit_failure_releases_claim_before_removing_pending_definition(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> list[str]:
            events.append("claim")
            return keys

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> int:
            events.append("release")
            return len(keys)

    async def _delete_task(_task_id: str) -> bool:
        events.append("delete_pending")
        return True

    mock_storage.create_task = AsyncMock()
    mock_storage.commit_attachment_update = AsyncMock(
        side_effect=RuntimeError("commit interrupted")
    )
    mock_storage.delete_task.side_effect = _delete_task
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords(), raising=False)

    with pytest.raises(RuntimeError, match="commit interrupted"):
        await service.create_task(
            _make_create_request(input_payload={"attachments": [{"key": "key-a"}]}),
            owner_id="user_1",
        )

    assert events == ["claim", "release", "delete_pending"]
    mock_scheduler.register_job.assert_not_called()


@pytest.mark.asyncio
async def test_create_task_registration_failure_soft_deletes_before_releasing_definition(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    created: ScheduledTask | None = None

    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> list[str]:
            return keys

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> int:
            events.append("release")
            return len(keys)

    async def _create_task(task: ScheduledTask) -> ScheduledTask:
        nonlocal created
        created = task
        return task

    async def _commit(*_args: Any) -> ScheduledTask:
        assert created is not None
        return created.model_copy(
            update={
                "enabled": True,
                "attachment_keys": ["key-a"],
                "pending_attachment_claim_keys": [],
                "attachment_setup_pending": False,
            }
        )

    async def _mark_deleted(_task_id: str) -> ScheduledTask:
        assert created is not None
        events.append("mark_deleted")
        return created.model_copy(
            update={
                "status": ScheduledTaskStatus.DELETED,
                "enabled": False,
                "attachment_keys": [],
                "pending_attachment_claim_keys": [],
                "pending_attachment_release_keys": ["key-a"],
                "attachment_setup_pending": False,
            }
        )

    async def _clear(_task_id: str, _keys: list[str]) -> bool:
        events.append("clear_pending")
        return True

    async def _finalize(_task_id: str) -> bool:
        events.append("finalize")
        return True

    mock_storage.create_task.side_effect = _create_task
    mock_storage.commit_attachment_update.side_effect = _commit
    mock_storage.mark_task_attachment_deletion.side_effect = _mark_deleted
    mock_storage.clear_pending_attachment_releases.side_effect = _clear
    mock_storage.finalize_deleted_task.side_effect = _finalize
    mock_scheduler.register_job.side_effect = RuntimeError("scheduler unavailable")
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords(), raising=False)

    with pytest.raises(RuntimeError, match="scheduler unavailable"):
        await service.create_task(
            _make_create_request(input_payload={"attachments": [{"key": "key-a"}]}),
            owner_id="user_1",
        )

    assert events == ["mark_deleted", "release", "clear_pending", "finalize"]


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
async def test_pause_task_unregisters(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    task = _make_task(attachment_keys=["key-a"])
    mock_storage.get_task = AsyncMock(return_value=task)
    mock_storage.update_task = AsyncMock(return_value=True)
    paused_task = _make_task(
        status=ScheduledTaskStatus.PAUSED,
        enabled=False,
        attachment_keys=["key-a"],
    )
    mock_storage.get_task = AsyncMock(side_effect=[task, paused_task])

    result = await service.pause_task("task_1")

    assert result == paused_task
    mock_storage.update_task.assert_called_once_with(
        "task_1",
        {"status": ScheduledTaskStatus.PAUSED, "enabled": False},
    )
    mock_scheduler.unregister_job.assert_called_once_with("task_1")
    assert result.attachment_keys == ["key-a"]


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
async def test_delete_task_soft_deletes_before_releasing_and_finalizing(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    task = _make_task(attachment_keys=["key-a"])
    deleted_task = task.model_copy(
        update={
            "status": ScheduledTaskStatus.DELETED,
            "enabled": False,
            "attachment_keys": [],
            "pending_attachment_release_keys": ["key-a"],
        }
    )

    class _FileRecords:
        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> int:
            assert keys == ["key-a"]
            assert uploaded_by == "user_1"
            events.append("release")
            return 1

    async def _mark(_task_id: str) -> ScheduledTask:
        events.append("mark_deleted")
        return deleted_task

    async def _clear(_task_id: str, _keys: list[str]) -> bool:
        events.append("clear_pending")
        return True

    async def _finalize(_task_id: str) -> bool:
        events.append("finalize")
        return True

    mock_storage.get_task = AsyncMock(return_value=task)
    mock_storage.mark_task_attachment_deletion.side_effect = _mark
    mock_storage.clear_pending_attachment_releases.side_effect = _clear
    mock_storage.finalize_deleted_task.side_effect = _finalize
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords(), raising=False)

    deleted = await service.delete_task("task_1")

    assert deleted is True
    mock_scheduler.unregister_job.assert_called_once_with("task_1")
    assert events == ["mark_deleted", "release", "clear_pending", "finalize"]
    mock_storage.delete_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_attachment_references_adopts_paused_legacy_definition(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    legacy = _make_task(
        status=ScheduledTaskStatus.PAUSED,
        enabled=False,
        input_payload={"attachments": [{"key": "key-a"}]},
        attachment_keys=[],
    )
    adopted = legacy.model_copy(update={"attachment_keys": ["key-a"]})

    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> list[str]:
            assert (keys, uploaded_by, task_id) == (["key-a"], "user_1", "task_1")
            events.append("claim")
            return keys

    async def _stage(_task_id: str, keys: list[str]) -> ScheduledTask:
        assert keys == ["key-a"]
        events.append("stage")
        return legacy.model_copy(update={"pending_attachment_claim_keys": keys})

    async def _commit(
        _task_id: str,
        updates: dict[str, Any],
        keys: list[str],
    ) -> ScheduledTask:
        assert updates == {}
        assert keys == ["key-a"]
        events.append("commit")
        return adopted

    mock_storage.list_attachment_reconciliation_tasks.return_value = [legacy]
    mock_storage.get_task.return_value = legacy
    mock_storage.stage_attachment_claim.side_effect = _stage
    mock_storage.commit_attachment_update.side_effect = _commit
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())

    reconciled = await service.reconcile_attachment_references()

    assert reconciled == 1
    assert events == ["stage", "claim", "commit"]
    mock_scheduler.register_job.assert_not_called()


@pytest.mark.asyncio
async def test_reconcile_attachment_references_retries_only_non_live_releases(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = _make_task(
        input_payload={"attachments": [{"key": "live-key"}]},
        attachment_keys=["live-key"],
        pending_attachment_release_keys=["live-key", "old-key"],
    )
    released: list[str] = []

    class _FileRecords:
        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> int:
            released.extend(keys)
            return len(keys)

    mock_storage.list_attachment_reconciliation_tasks.return_value = [task]
    mock_storage.get_task.return_value = task
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())

    reconciled = await service.reconcile_attachment_references()

    assert reconciled == 1
    assert released == ["old-key"]
    mock_storage.clear_pending_attachment_releases.assert_awaited_once_with(
        "task_1", ["old-key"]
    )


@pytest.mark.asyncio
async def test_reconcile_attachment_references_removes_interrupted_create(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provisional = _make_task(
        enabled=False,
        input_payload={"attachments": [{"key": "key-a"}]},
        pending_attachment_claim_keys=["key-a"],
        attachment_setup_pending=True,
    )
    deleted = provisional.model_copy(
        update={
            "status": ScheduledTaskStatus.DELETED,
            "pending_attachment_claim_keys": [],
            "pending_attachment_release_keys": ["key-a"],
            "attachment_setup_pending": False,
        }
    )
    events: list[str] = []

    class _FileRecords:
        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> int:
            events.append("release")
            return len(keys)

    async def _mark(_task_id: str) -> ScheduledTask:
        events.append("mark_deleted")
        return deleted

    async def _clear(_task_id: str, _keys: list[str]) -> bool:
        events.append("clear")
        return True

    async def _finalize(_task_id: str) -> bool:
        events.append("finalize")
        return True

    mock_storage.list_attachment_reconciliation_tasks.return_value = [provisional]
    mock_storage.get_task.return_value = provisional
    mock_storage.mark_task_attachment_deletion.side_effect = _mark
    mock_storage.clear_pending_attachment_releases.side_effect = _clear
    mock_storage.finalize_deleted_task.side_effect = _finalize
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())

    reconciled = await service.reconcile_attachment_references()

    assert reconciled == 1
    assert events == ["mark_deleted", "release", "clear", "finalize"]


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
async def test_update_task_claims_new_attachment_before_releasing_removed_key(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    original = _make_task(
        input_payload={"attachments": [{"key": "old-key"}]},
        attachment_keys=["old-key"],
    )
    updated = _make_task(
        input_payload={"attachments": [{"key": "new-key"}]},
        attachment_keys=["new-key"],
        pending_attachment_release_keys=["old-key"],
    )

    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> list[str]:
            assert keys == ["new-key"]
            assert uploaded_by == "user_1"
            events.append("claim_new")
            return keys

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> int:
            assert keys == ["old-key"]
            assert uploaded_by == "user_1"
            events.append("release_old")
            return len(keys)

    async def _stage(_task_id: str, keys: list[str]) -> ScheduledTask:
        assert keys == ["new-key"]
        events.append("stage_claim")
        return original.model_copy(update={"pending_attachment_claim_keys": keys})

    async def _commit(
        _task_id: str,
        updates: dict[str, Any],
        keys: list[str],
    ) -> ScheduledTask:
        assert updates["input_payload"] == updated.input_payload
        assert keys == ["new-key"]
        events.append("commit_input")
        return updated

    async def _clear(_task_id: str, keys: list[str]) -> bool:
        assert keys == ["old-key"]
        events.append("clear_release")
        return True

    mock_storage.get_task = AsyncMock(return_value=original)
    mock_storage.stage_attachment_claim.side_effect = _stage
    mock_storage.commit_attachment_update.side_effect = _commit
    mock_storage.clear_pending_attachment_releases.side_effect = _clear
    mock_scheduler.register_job.side_effect = lambda _job: events.append("register")
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords(), raising=False)

    result = await service.update_task(
        "task_1",
        _make_update_request(input_payload=updated.input_payload),
    )

    assert result == updated
    assert events == [
        "stage_claim",
        "claim_new",
        "commit_input",
        "register",
        "release_old",
        "clear_release",
    ]


@pytest.mark.asyncio
async def test_update_task_missing_after_claim_rolls_back_staged_token(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    original = _make_task(attachment_keys=[])

    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> list[str]:
            events.append("claim")
            return keys

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
        ) -> int:
            events.append("rollback")
            return len(keys)

    async def _clear(_task_id: str, _keys: list[str]) -> bool:
        events.append("clear_pending")
        return True

    mock_storage.get_task = AsyncMock(return_value=original)
    mock_storage.stage_attachment_claim = AsyncMock(return_value=original)
    mock_storage.commit_attachment_update = AsyncMock(return_value=None)
    mock_storage.clear_pending_attachment_claims.side_effect = _clear
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords(), raising=False)

    result = await service.update_task(
        "task_1",
        _make_update_request(input_payload={"attachments": [{"key": "key-a"}]}),
    )

    assert result is None
    assert events == ["claim", "rollback", "clear_pending"]


@pytest.mark.asyncio
async def test_attachment_update_fails_closed_when_definition_is_being_mutated(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _contended(_task_id: str) -> None:
        return None

    monkeypatch.setattr(service_module, "acquire_attachment_mutation_lock", _contended)

    with pytest.raises(ValueError, match="attachment mutation is already in progress"):
        await service.update_task(
            "task_1",
            _make_update_request(input_payload={"attachments": [{"key": "key-a"}]}),
        )

    mock_storage.get_task.assert_not_awaited()


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
