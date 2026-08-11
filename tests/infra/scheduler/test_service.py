"""Tests for ScheduledTaskService business logic."""

from __future__ import annotations

import asyncio
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


def _with_attachment_fence(
    task: ScheduledTask,
    *,
    token: str = "mutation-token",
    generation: int = 1,
) -> ScheduledTask:
    return task.model_copy(
        update={
            "attachment_mutation_token": token,
            "attachment_mutation_generation": generation,
        }
    )


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

    async def _extend(_task_id: str, _token: str, *, ttl: int) -> bool:
        return True

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
    monkeypatch.setattr(
        service_module,
        "extend_attachment_mutation_lock",
        _extend,
        raising=False,
    )


@pytest.mark.asyncio
async def test_attachment_mutation_context_renews_lock_until_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extended = asyncio.Event()
    events: list[str] = []

    async def _acquire(_task_id: str) -> str:
        events.append("acquire")
        return "owner-token"

    async def _extend(task_id: str, token: str, *, ttl: int) -> bool:
        assert (task_id, token, ttl) == (
            "task_1",
            "owner-token",
            service_module.ATTACHMENT_MUTATION_LOCK_TTL,
        )
        events.append("extend")
        extended.set()
        return True

    async def _release(_task_id: str, _token: str) -> None:
        events.append("release")

    monkeypatch.setattr(service_module, "acquire_attachment_mutation_lock", _acquire)
    monkeypatch.setattr(service_module, "extend_attachment_mutation_lock", _extend, raising=False)
    monkeypatch.setattr(service_module, "release_attachment_mutation_lock", _release)
    monkeypatch.setattr(
        service_module,
        "ATTACHMENT_MUTATION_RENEW_INTERVAL_SECONDS",
        0,
        raising=False,
    )

    async with service_module._attachment_mutation("task_1") as token:
        assert token == "owner-token"
        await asyncio.wait_for(extended.wait(), timeout=0.1)

    assert events[0:2] == ["acquire", "extend"]
    assert events[-1] == "release"


@pytest.mark.asyncio
async def test_attachment_mutation_context_aborts_when_lock_ownership_is_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    released = asyncio.Event()

    async def _acquire(_task_id: str) -> str:
        return "owner-token"

    async def _extend(_task_id: str, _token: str, *, ttl: int) -> bool:
        return False

    async def _release(_task_id: str, _token: str) -> None:
        released.set()

    monkeypatch.setattr(service_module, "acquire_attachment_mutation_lock", _acquire)
    monkeypatch.setattr(service_module, "extend_attachment_mutation_lock", _extend)
    monkeypatch.setattr(service_module, "release_attachment_mutation_lock", _release)
    monkeypatch.setattr(service_module, "ATTACHMENT_MUTATION_RENEW_INTERVAL_SECONDS", 0)

    with pytest.raises(RuntimeError, match="mutation lock was lost"):
        async with service_module._attachment_mutation("task_1"):
            await asyncio.Future()

    assert released.is_set()


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

        async def _claim_attachment_mutation(
            task_id: str,
            token: str,
        ) -> ScheduledTask | None:
            create_call = storage.create_task.await_args
            if create_call is not None and create_call.args[0].id == task_id:
                task = create_call.args[0]
            else:
                task = await storage.get_task(task_id)
            if task is None:
                return None
            return _with_attachment_fence(task, token=token)

        storage.claim_attachment_mutation.side_effect = _claim_attachment_mutation
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
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert keys == ["key-a"]
            assert uploaded_by == "user_1"
            assert task_id
            assert mutation_generation == 1
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
        *,
        fence: Any,
    ) -> ScheduledTask:
        assert persisted is not None
        assert task_id == persisted.id
        assert updates == {"enabled": True}
        assert attachment_keys == ["key-a"]
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("commit_active")
        return persisted.model_copy(
            update={
                "enabled": True,
                "attachment_keys": ["key-a"],
                "pending_attachment_claim_keys": [],
                "attachment_setup_pending": False,
            }
        )

    async def _claim_fence(task_id: str, token: str) -> ScheduledTask:
        assert persisted is not None
        assert task_id == persisted.id
        assert token == "mutation-token"
        events.append("claim_fence")
        return persisted.model_copy(
            update={
                "attachment_mutation_token": token,
                "attachment_mutation_generation": 1,
            }
        )

    mock_storage.create_task.side_effect = _create_task
    mock_storage.claim_attachment_mutation.side_effect = _claim_fence
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
    assert events == [
        "persist_pending",
        "claim_fence",
        "claim",
        "commit_active",
        "register",
    ]


@pytest.mark.asyncio
async def test_create_task_ambiguous_claim_soft_deletes_before_releasing_definition(
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
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert mutation_generation == 1
            events.append("claim_ambiguous")
            raise service_module.AttachmentClaimError()

        async def adopt_scheduled_task_reference_generation(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            events.append("adopt")
            return len(keys)

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            events.append("release")
            return len(keys)

    async def _mark(task_id: str, *, fence: Any) -> ScheduledTask:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("mark_deleted")
        return _make_task(
            _id=task_id,
            status=ScheduledTaskStatus.DELETED,
            enabled=False,
            pending_attachment_release_keys=["key-a"],
        )

    async def _clear(_task_id: str, _keys: list[str], *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("clear")
        return True

    async def _finalize(_task_id: str, *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("finalize")
        return True

    mock_storage.create_task = AsyncMock()
    mock_storage.delete_task = AsyncMock(return_value=True)
    mock_storage.mark_task_attachment_deletion.side_effect = _mark
    mock_storage.clear_pending_attachment_releases.side_effect = _clear
    mock_storage.finalize_deleted_task.side_effect = _finalize
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords(), raising=False)
    request = _make_create_request(
        input_payload={"attachments": [{"key": "key-a"}]},
    )

    with pytest.raises(service_module.AttachmentClaimError):
        await service.create_task(request, owner_id="user_1")

    created_task = mock_storage.create_task.await_args.args[0]
    assert created_task.enabled is False
    assert created_task.attachment_setup_pending is True
    assert events == [
        "claim_ambiguous",
        "mark_deleted",
        "adopt",
        "release",
        "clear",
        "finalize",
    ]
    mock_storage.delete_task.assert_not_awaited()
    mock_scheduler.register_job.assert_not_called()


@pytest.mark.asyncio
async def test_create_task_ambiguous_commit_failure_retains_claim_for_reconciliation(
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
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert mutation_generation == 1
            events.append("claim")
            return keys

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            events.append("release")
            return len(keys)

    mock_storage.create_task = AsyncMock()
    mock_storage.commit_attachment_update = AsyncMock(
        side_effect=ConnectionError("commit reply lost")
    )
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords(), raising=False)

    with pytest.raises(ConnectionError, match="commit reply lost"):
        await service.create_task(
            _make_create_request(input_payload={"attachments": [{"key": "key-a"}]}),
            owner_id="user_1",
        )

    assert events == ["claim"]
    mock_storage.delete_task.assert_not_awaited()
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
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert mutation_generation == 1
            return keys

        async def adopt_scheduled_task_reference_generation(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            events.append("adopt")
            return len(keys)

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            events.append("release")
            return len(keys)

    async def _create_task(task: ScheduledTask) -> ScheduledTask:
        nonlocal created
        created = task
        return task

    async def _commit(*_args: Any, fence: Any) -> ScheduledTask:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        assert created is not None
        return created.model_copy(
            update={
                "enabled": True,
                "attachment_keys": ["key-a"],
                "pending_attachment_claim_keys": [],
                "attachment_setup_pending": False,
            }
        )

    async def _mark_deleted(_task_id: str, *, fence: Any) -> ScheduledTask:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
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

    async def _clear(_task_id: str, _keys: list[str], *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("clear_pending")
        return True

    async def _finalize(_task_id: str, *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
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

    assert events == [
        "mark_deleted",
        "adopt",
        "release",
        "clear_pending",
        "finalize",
    ]


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
async def test_update_task_does_not_mutate_deleted_definition(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    deleted = _make_task(status=ScheduledTaskStatus.DELETED, enabled=False)
    mock_storage.get_task.return_value = deleted

    result = await service.update_task("task_1", _make_update_request(name="new"))

    assert result is None
    mock_storage.update_task.assert_not_awaited()
    mock_scheduler.register_job.assert_not_called()


@pytest.mark.asyncio
async def test_pause_task_does_not_mutate_deleted_definition(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    mock_storage.get_task.return_value = _make_task(
        status=ScheduledTaskStatus.DELETED,
        enabled=False,
    )

    result = await service.pause_task("task_1")

    assert result is None
    mock_storage.update_task.assert_not_awaited()
    mock_scheduler.unregister_job.assert_not_called()


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
async def test_resume_task_does_not_mutate_deleted_definition(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
) -> None:
    mock_storage.get_task.return_value = _make_task(
        status=ScheduledTaskStatus.DELETED,
        enabled=False,
    )

    result = await service.resume_task("task_1")

    assert result is None
    mock_storage.update_task.assert_not_awaited()
    mock_scheduler.register_job.assert_not_called()


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
        async def adopt_scheduled_task_reference_generation(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert keys == ["key-a"]
            assert uploaded_by == "user_1"
            assert mutation_generation == 1
            events.append("adopt")
            return 1

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert keys == ["key-a"]
            assert uploaded_by == "user_1"
            assert mutation_generation == 1
            events.append("release")
            return 1

    async def _mark(_task_id: str, *, fence: Any) -> ScheduledTask:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("mark_deleted")
        return deleted_task

    async def _clear(_task_id: str, _keys: list[str], *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("clear_pending")
        return True

    async def _finalize(_task_id: str, *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
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
    assert events == [
        "mark_deleted",
        "adopt",
        "release",
        "clear_pending",
        "finalize",
    ]
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
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert (keys, uploaded_by, task_id) == (["key-a"], "user_1", "task_1")
            assert mutation_generation == 1
            events.append("claim")
            return keys

    async def _stage(_task_id: str, keys: list[str], *, fence: Any) -> ScheduledTask:
        assert keys == ["key-a"]
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("stage")
        return legacy.model_copy(update={"pending_attachment_claim_keys": keys})

    async def _commit(
        _task_id: str,
        updates: dict[str, Any],
        keys: list[str],
        *,
        fence: Any,
    ) -> ScheduledTask:
        assert updates == {}
        assert keys == ["key-a"]
        assert (fence.token, fence.generation) == ("mutation-token", 1)
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
async def test_reconcile_ambiguous_commit_failure_retains_claim_and_marker(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _make_task(
        status=ScheduledTaskStatus.PAUSED,
        enabled=False,
        input_payload={"attachments": [{"key": "key-a"}]},
        attachment_keys=[],
    )
    pending = legacy.model_copy(update={"pending_attachment_claim_keys": ["key-a"]})
    events: list[str] = []

    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert mutation_generation == 1
            events.append("claim")
            return keys

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            events.append("release")
            return len(keys)

    mock_storage.list_attachment_reconciliation_tasks.return_value = [legacy]
    mock_storage.get_task.return_value = legacy
    mock_storage.stage_attachment_claim.return_value = pending
    mock_storage.commit_attachment_update.side_effect = ConnectionError(
        "commit outcome unavailable"
    )
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())

    with pytest.raises(ConnectionError, match="commit outcome unavailable"):
        await service.reconcile_attachment_references()

    assert events == ["claim"]
    mock_storage.clear_pending_attachment_claims.assert_not_awaited()


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
        async def adopt_scheduled_task_reference_generation(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            return len(keys)

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            released.extend(keys)
            return len(keys)

    mock_storage.list_attachment_reconciliation_tasks.return_value = [task]
    mock_storage.get_task.return_value = task
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())

    reconciled = await service.reconcile_attachment_references()

    assert reconciled == 1
    assert released == ["old-key"]
    clear_call = mock_storage.clear_pending_attachment_releases.await_args
    assert clear_call.args == ("task_1", ["old-key"])
    assert (clear_call.kwargs["fence"].token, clear_call.kwargs["fence"].generation) == (
        "mutation-token",
        1,
    )


@pytest.mark.asyncio
async def test_pending_attachment_releases_are_cleared_one_bounded_chunk_at_a_time(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_a = [f"a-{index}" for index in range(100)]
    old_b = [f"b-{index}" for index in range(100)]
    task = _make_task(
        input_payload={"attachments": [{"key": f"c-{index}"} for index in range(100)]},
        attachment_keys=[f"c-{index}" for index in range(100)],
        pending_attachment_release_keys=old_a + old_b,
    )
    released_chunks: list[list[str]] = []
    cleared_chunks: list[list[str]] = []
    fence = service_module.AttachmentMutationFence("mutation-token", 3)

    class _FileRecords:
        async def adopt_scheduled_task_reference_generation(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == fence.generation
            return len(keys)

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert len(keys) <= service_module.REFERENCE_KEYS_MAX
            assert mutation_generation == fence.generation
            released_chunks.append(list(keys))
            return len(keys)

    async def _clear(_task_id: str, keys: list[str], *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 3)
        cleared_chunks.append(list(keys))
        return True

    mock_storage.clear_pending_attachment_releases.side_effect = _clear
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())

    released = await service._release_pending_attachment_references(task, fence)

    assert released == 200
    assert released_chunks == [old_a, old_b]
    assert cleared_chunks == [old_a, old_b]


@pytest.mark.asyncio
async def test_pending_attachment_release_retry_keeps_failed_chunk_durable(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_a = [f"a-{index}" for index in range(100)]
    old_b = [f"b-{index}" for index in range(100)]
    task = _make_task(pending_attachment_release_keys=old_a + old_b)
    cleared_chunks: list[list[str]] = []
    fail_b = True
    fence = service_module.AttachmentMutationFence("mutation-token", 3)

    class _FileRecords:
        async def adopt_scheduled_task_reference_generation(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == fence.generation
            return len(keys)

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == fence.generation
            nonlocal fail_b
            if keys == old_b and fail_b:
                raise RuntimeError("file record write interrupted")
            return len(keys)

    async def _clear(_task_id: str, keys: list[str], *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 3)
        cleared_chunks.append(list(keys))
        return True

    mock_storage.clear_pending_attachment_releases.side_effect = _clear
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())

    with pytest.raises(RuntimeError, match="write interrupted"):
        await service._release_pending_attachment_references(task, fence)

    assert cleared_chunks == [old_a]
    fail_b = False
    retried = await service._release_pending_attachment_references(
        task.model_copy(update={"pending_attachment_release_keys": old_b}),
        fence,
    )

    assert retried == 100
    assert cleared_chunks == [old_a, old_b]


@pytest.mark.asyncio
async def test_pending_attachment_claim_retry_keeps_failed_chunk_durable(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_a = [f"a-{index}" for index in range(100)]
    old_b = [f"b-{index}" for index in range(100)]
    task = _make_task(pending_attachment_claim_keys=old_a + old_b)
    fence = service_module.AttachmentMutationFence("mutation-token", 3)
    adopted_chunks: list[list[str]] = []
    released_chunks: list[list[str]] = []
    cleared_chunks: list[list[str]] = []
    fail_b = True

    class _FileRecords:
        async def adopt_scheduled_task_reference_generation(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert len(keys) <= service_module.REFERENCE_KEYS_MAX
            assert mutation_generation == fence.generation
            adopted_chunks.append(list(keys))
            return len(keys)

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            nonlocal fail_b
            assert len(keys) <= service_module.REFERENCE_KEYS_MAX
            assert mutation_generation == fence.generation
            released_chunks.append(list(keys))
            if keys == old_b and fail_b:
                raise RuntimeError("file record write interrupted")
            return len(keys)

    async def _clear(_task_id: str, keys: list[str], *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 3)
        cleared_chunks.append(list(keys))
        return True

    mock_storage.clear_pending_attachment_claims.side_effect = _clear
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())

    with pytest.raises(RuntimeError, match="write interrupted"):
        await service._reconcile_attachment_task(mock_storage, task, fence)

    assert adopted_chunks == [old_a, old_b]
    assert released_chunks == [old_a, old_b]
    assert cleared_chunks == [old_a]

    fail_b = False
    await service._reconcile_attachment_task(
        mock_storage,
        task.model_copy(update={"pending_attachment_claim_keys": old_b}),
        fence,
    )

    assert adopted_chunks == [old_a, old_b, old_b]
    assert released_chunks == [old_a, old_b, old_b]
    assert cleared_chunks == [old_a, old_b]


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
        async def adopt_scheduled_task_reference_generation(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            events.append("adopt")
            return len(keys)

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            events.append("release")
            return len(keys)

    async def _mark(_task_id: str, *, fence: Any) -> ScheduledTask:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("mark_deleted")
        return deleted

    async def _clear(_task_id: str, _keys: list[str], *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        events.append("clear")
        return True

    async def _finalize(_task_id: str, *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
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
    assert events == ["mark_deleted", "adopt", "release", "clear", "finalize"]


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
    owned = original.model_copy(
        update={
            "attachment_mutation_token": "mutation-token",
            "attachment_mutation_generation": 7,
        }
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
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert keys == ["new-key"]
            assert uploaded_by == "user_1"
            assert mutation_generation == 7
            events.append("claim_new")
            return keys

        async def adopt_scheduled_task_reference_generation(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert keys == ["old-key"]
            assert mutation_generation == 7
            events.append("adopt_old")
            return len(keys)

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert keys == ["old-key"]
            assert uploaded_by == "user_1"
            assert mutation_generation == 7
            events.append("release_old")
            return len(keys)

    async def _claim_fence(_task_id: str, token: str) -> ScheduledTask:
        assert token == "mutation-token"
        events.append("claim_fence")
        return owned

    async def _stage(
        _task_id: str,
        keys: list[str],
        *,
        fence: Any,
    ) -> ScheduledTask:
        assert keys == ["new-key"]
        assert (fence.token, fence.generation) == ("mutation-token", 7)
        events.append("stage_claim")
        return original.model_copy(update={"pending_attachment_claim_keys": keys})

    async def _commit(
        _task_id: str,
        updates: dict[str, Any],
        keys: list[str],
        *,
        fence: Any,
    ) -> ScheduledTask:
        assert updates["input_payload"] == updated.input_payload
        assert keys == ["new-key"]
        assert (fence.token, fence.generation) == ("mutation-token", 7)
        events.append("commit_input")
        return updated

    async def _clear(_task_id: str, keys: list[str], *, fence: Any) -> bool:
        assert keys == ["old-key"]
        assert (fence.token, fence.generation) == ("mutation-token", 7)
        events.append("clear_release")
        return True

    mock_storage.claim_attachment_mutation.side_effect = _claim_fence
    mock_storage.get_task = AsyncMock(return_value=owned)
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
        "claim_fence",
        "stage_claim",
        "claim_new",
        "commit_input",
        "register",
        "adopt_old",
        "release_old",
        "clear_release",
    ]


@pytest.mark.asyncio
async def test_update_task_ambiguous_commit_failure_retains_live_claim(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _make_task(attachment_keys=[])
    state = original
    scheduled_task_reference_ids: set[str] = set()

    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert mutation_generation == 1
            scheduled_task_reference_ids.add(task_id)
            return keys

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            scheduled_task_reference_ids.discard(task_id)
            return len(keys)

    async def _stage(_task_id: str, keys: list[str], *, fence: Any) -> ScheduledTask:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        nonlocal state
        state = state.model_copy(update={"pending_attachment_claim_keys": list(keys)})
        return state

    async def _commit(
        _task_id: str,
        updates: dict[str, Any],
        keys: list[str],
        *,
        fence: Any,
    ) -> ScheduledTask:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        nonlocal state
        state = state.model_copy(
            update={
                **updates,
                "attachment_keys": list(keys),
                "pending_attachment_claim_keys": [],
            }
        )
        raise ConnectionError("commit reply lost")

    async def _clear(_task_id: str, keys: list[str], *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
        nonlocal state
        state = state.model_copy(
            update={
                "pending_attachment_claim_keys": [
                    key for key in state.pending_attachment_claim_keys if key not in keys
                ]
            }
        )
        return True

    mock_storage.get_task.return_value = original
    mock_storage.stage_attachment_claim.side_effect = _stage
    mock_storage.commit_attachment_update.side_effect = _commit
    mock_storage.clear_pending_attachment_claims.side_effect = _clear
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())

    with pytest.raises(ConnectionError, match="commit reply lost"):
        await service.update_task(
            "task_1",
            _make_update_request(
                input_payload={"attachments": [{"key": "key-b"}]}
            ),
        )

    assert state.attachment_keys == ["key-b"]
    assert state.pending_attachment_claim_keys == []
    assert scheduled_task_reference_ids == {"task_1"}
    mock_storage.clear_pending_attachment_claims.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_task_lock_loss_does_not_release_successor_live_claim(
    service: ScheduledTaskService,
    mock_storage: AsyncMock,
    mock_scheduler: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = _make_task(attachment_keys=[])
    scheduled_task_reference_ids: set[str] = set()
    first_commit_started = asyncio.Event()
    lose_first_lock = asyncio.Event()
    acquire_count = 0
    commit_count = 0

    async def _acquire(_task_id: str) -> str:
        nonlocal acquire_count
        acquire_count += 1
        return f"owner-{acquire_count}"

    async def _extend(_task_id: str, token: str, *, ttl: int) -> bool:
        if token == "owner-1":
            await lose_first_lock.wait()
            return False
        return True

    async def _release(_task_id: str, _token: str) -> None:
        return None

    class _FileRecords:
        async def claim_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert mutation_generation >= 1
            newly_claimed = task_id not in scheduled_task_reference_ids
            scheduled_task_reference_ids.add(task_id)
            return list(keys) if newly_claimed else []

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation >= 1
            existed = task_id in scheduled_task_reference_ids
            scheduled_task_reference_ids.discard(task_id)
            return int(existed)

    async def _get(_task_id: str) -> ScheduledTask:
        return state

    async def _claim_fence(_task_id: str, token: str) -> ScheduledTask:
        nonlocal state
        generation = state.attachment_mutation_generation
        if state.attachment_mutation_token != token:
            generation += 1
        state = _with_attachment_fence(
            state,
            token=token,
            generation=generation,
        )
        return state

    async def _stage(_task_id: str, keys: list[str], *, fence: Any) -> ScheduledTask:
        nonlocal state
        assert (state.attachment_mutation_token, state.attachment_mutation_generation) == (
            fence.token,
            fence.generation,
        )
        state = state.model_copy(
            update={
                "pending_attachment_claim_keys": list(
                    dict.fromkeys([*state.pending_attachment_claim_keys, *keys])
                )
            }
        )
        return state

    async def _commit(
        _task_id: str,
        updates: dict[str, Any],
        keys: list[str],
        *,
        fence: Any,
    ) -> ScheduledTask:
        nonlocal commit_count, state
        assert (state.attachment_mutation_token, state.attachment_mutation_generation) == (
            fence.token,
            fence.generation,
        )
        commit_count += 1
        if commit_count == 1:
            first_commit_started.set()
            await asyncio.Future()
        state = state.model_copy(
            update={
                **updates,
                "attachment_keys": list(keys),
                "pending_attachment_claim_keys": [],
            }
        )
        return state

    async def _clear(_task_id: str, keys: list[str], *, fence: Any) -> bool:
        nonlocal state
        assert (state.attachment_mutation_token, state.attachment_mutation_generation) == (
            fence.token,
            fence.generation,
        )
        state = state.model_copy(
            update={
                "pending_attachment_claim_keys": [
                    key for key in state.pending_attachment_claim_keys if key not in keys
                ]
            }
        )
        return True

    mock_storage.get_task.side_effect = _get
    mock_storage.claim_attachment_mutation.side_effect = _claim_fence
    mock_storage.stage_attachment_claim.side_effect = _stage
    mock_storage.commit_attachment_update.side_effect = _commit
    mock_storage.clear_pending_attachment_claims.side_effect = _clear
    monkeypatch.setattr(service_module, "acquire_attachment_mutation_lock", _acquire)
    monkeypatch.setattr(service_module, "extend_attachment_mutation_lock", _extend)
    monkeypatch.setattr(service_module, "release_attachment_mutation_lock", _release)
    monkeypatch.setattr(service_module, "ATTACHMENT_MUTATION_RENEW_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(service_module, "FileRecordStorage", lambda: _FileRecords())
    request = _make_update_request(
        input_payload={"attachments": [{"key": "key-b"}]}
    )

    stale_writer = asyncio.create_task(service.update_task("task_1", request))
    await asyncio.wait_for(first_commit_started.wait(), timeout=1)
    successor = await service.update_task("task_1", request)
    assert successor is not None
    assert successor.attachment_keys == ["key-b"]

    lose_first_lock.set()
    with pytest.raises(RuntimeError, match="mutation lock was lost"):
        await stale_writer

    assert state.attachment_keys == ["key-b"]
    assert scheduled_task_reference_ids == {"task_1"}
    mock_scheduler.register_job.assert_called_once()


@pytest.mark.asyncio
async def test_update_task_missing_after_claim_retains_staged_token(
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
            *,
            mutation_generation: int,
        ) -> list[str]:
            assert mutation_generation == 1
            events.append("claim")
            return keys

        async def release_scheduled_task_references(
            self,
            keys: list[str],
            uploaded_by: str,
            task_id: str,
            *,
            mutation_generation: int,
        ) -> int:
            assert mutation_generation == 1
            events.append("rollback")
            return len(keys)

    async def _clear(_task_id: str, _keys: list[str], *, fence: Any) -> bool:
        assert (fence.token, fence.generation) == ("mutation-token", 1)
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
    assert events == ["claim"]
    mock_storage.clear_pending_attachment_claims.assert_not_awaited()


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
