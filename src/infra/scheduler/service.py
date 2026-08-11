"""Business logic for scheduled task CRUD and scheduler coordination.

This service is the bridge between the API layer and the lower-level
storage, runner, and scheduler components.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.infra.logging import get_logger
from src.infra.scheduler.locks import (
    ATTACHMENT_MUTATION_LOCK_TTL,
    acquire_attachment_mutation_lock,
    extend_attachment_mutation_lock,
    release_attachment_mutation_lock,
)
from src.infra.scheduler.runner import get_scheduled_task_runner
from src.infra.scheduler.runtime import ScheduledJob, get_runtime_scheduler
from src.infra.scheduler.storage import AttachmentMutationFence, get_scheduled_task_storage
from src.infra.session.storage import SessionStorage
from src.infra.upload.file_record import (
    REFERENCE_KEYS_MAX,
    AttachmentClaimError,
    FileRecordStorage,
)
from src.infra.utils.datetime import ensure_utc, utc_now
from src.infra.writer.presenter_config import _extract_attachment_keys
from src.kernel.schemas.scheduled_task import (
    CronTriggerConfig,
    DateTriggerConfig,
    IntervalTriggerConfig,
    ScheduledTask,
    ScheduledTaskCreate,
    ScheduledTaskResponse,
    ScheduledTaskStatus,
    ScheduledTaskUpdate,
    TaskRunResponse,
    TriggerType,
)

logger = get_logger(__name__)

_managed_task_signatures: dict[str, str] = {}
ATTACHMENT_MUTATION_RENEW_INTERVAL_SECONDS = ATTACHMENT_MUTATION_LOCK_TTL // 3


@asynccontextmanager
async def _attachment_mutation(task_id: str) -> AsyncIterator[str]:
    token = await acquire_attachment_mutation_lock(task_id)
    if token is None:
        raise ValueError("Scheduled task attachment mutation is already in progress")
    owner_task = asyncio.current_task()
    lock_lost = asyncio.Event()

    async def _renew_lock() -> None:
        while True:
            await asyncio.sleep(ATTACHMENT_MUTATION_RENEW_INTERVAL_SECONDS)
            try:
                extended = await extend_attachment_mutation_lock(
                    task_id,
                    token,
                    ttl=ATTACHMENT_MUTATION_LOCK_TTL,
                )
            except Exception:
                logger.exception(
                    "[Service] attachment mutation lock renewal failed for task %s",
                    task_id,
                )
                extended = False
            if not extended:
                lock_lost.set()
                if owner_task is not None:
                    owner_task.cancel()
                return

    renewal_task = asyncio.create_task(_renew_lock())
    try:
        try:
            yield token
        except asyncio.CancelledError:
            if lock_lost.is_set():
                raise RuntimeError(
                    f"Scheduled task attachment mutation lock was lost for {task_id}"
                ) from None
            raise
    finally:
        renewal_task.cancel()
        await asyncio.gather(renewal_task, return_exceptions=True)
        await release_attachment_mutation_lock(task_id, token)


def _task_attachment_keys(input_payload: dict[str, Any]) -> list[str]:
    raw_attachments = input_payload.get("attachments")
    attachments = (
        [dict(item) for item in raw_attachments if isinstance(item, dict)]
        if isinstance(raw_attachments, list)
        else []
    )
    keys = _extract_attachment_keys(attachments, limit=None)
    if len(keys) > REFERENCE_KEYS_MAX:
        raise AttachmentClaimError()
    return keys


def _attachment_fence(task: ScheduledTask, token: str) -> AttachmentMutationFence:
    if (
        task.attachment_mutation_token != token
        or task.attachment_mutation_generation < 1
    ):
        raise RuntimeError(f"Scheduled task attachment mutation fence was lost for {task.id}")
    return AttachmentMutationFence(
        token=token,
        generation=task.attachment_mutation_generation,
    )


def _coerce_timezone(timezone_name: str | None) -> ZoneInfo:
    name = (timezone_name or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Invalid timezone: {name}") from exc


def _ensure_utc_in_timezone(dt, timezone_name: str | None):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_coerce_timezone(timezone_name))
    return ensure_utc(dt)


def clear_managed_task_signatures() -> None:
    """Release in-process scheduler registration signatures."""
    _managed_task_signatures.clear()


class ScheduledTaskService:
    """CRUD + scheduler orchestration for dynamic scheduled tasks."""

    def __init__(self) -> None:
        self._active_tasks_marker: int | None = None
        self._active_task_count = 0

    # ── CRUD ───────────────────────────────────────

    async def create_task(
        self,
        request: ScheduledTaskCreate,
        owner_id: str,
    ) -> ScheduledTask:
        """Validate, persist, and register a new scheduled task."""
        # Validate trigger config
        self._build_trigger(request.trigger_type, request.trigger_config, request.timezone)
        attachment_keys = _task_attachment_keys(request.input_payload)

        now = utc_now()
        task_id = str(uuid4())
        task = ScheduledTask.model_validate(
            {
                "_id": task_id,
                "name": request.name,
                "description": request.description,
                "agent_id": request.agent_id,
                "trigger_type": request.trigger_type,
                "trigger_config": request.trigger_config,
                "timezone": request.timezone,
                "input_payload": request.input_payload,
                "status": ScheduledTaskStatus.ACTIVE,
                "enabled": False if attachment_keys else request.enabled,
                "run_on_start": False
                if request.trigger_type == TriggerType.DATE
                else request.run_on_start,
                "max_retries": request.max_retries,
                "timeout_seconds": request.timeout_seconds,
                "owner_id": owner_id,
                "attachment_keys": [],
                "pending_attachment_claim_keys": attachment_keys,
                "attachment_setup_pending": bool(attachment_keys),
                "source_session_id": request.source_session_id,
                "source_run_id": request.source_run_id,
                "created_by": request.created_by,
                "delivery": request.delivery,
                "created_at": now,
                "updated_at": now,
            }
        )

        if attachment_keys:
            async with _attachment_mutation(task_id) as token:
                return await self._persist_created_task(
                    task,
                    request,
                    attachment_keys,
                    mutation_token=token,
                )
        return await self._persist_created_task(
            task,
            request,
            attachment_keys,
            mutation_token=None,
        )

    async def _persist_created_task(
        self,
        task: ScheduledTask,
        request: ScheduledTaskCreate,
        attachment_keys: list[str],
        *,
        mutation_token: str | None,
    ) -> ScheduledTask:
        storage = get_scheduled_task_storage()
        await storage.create_task(task)
        fence: AttachmentMutationFence | None = None
        if attachment_keys:
            if mutation_token is None:
                raise RuntimeError("Attachment create requires a mutation token")
            owned_task = await storage.claim_attachment_mutation(task.id, mutation_token)
            if owned_task is None:
                raise RuntimeError("Scheduled task disappeared during attachment setup")
            fence = _attachment_fence(owned_task, mutation_token)
            task = owned_task
            file_records = FileRecordStorage()
            try:
                await file_records.claim_scheduled_task_references(
                    attachment_keys,
                    task.owner_id,
                    task.id,
                    mutation_generation=fence.generation,
                )
            except (Exception, asyncio.CancelledError):
                try:
                    deleted_task = await storage.mark_task_attachment_deletion(
                        task.id,
                        fence=fence,
                    )
                    if deleted_task is not None:
                        await self._release_pending_attachment_references(
                            deleted_task,
                            fence,
                        )
                except Exception:
                    logger.exception(
                        "[Service] failed to reconcile ambiguous task attachment claim %s",
                        task.id,
                    )
                raise
            try:
                committed = await storage.commit_attachment_update(
                    task.id,
                    {"enabled": request.enabled},
                    attachment_keys,
                    fence=fence,
                )
                if committed is None:
                    raise RuntimeError("Scheduled task attachment setup was interrupted")
            except (Exception, asyncio.CancelledError):
                logger.warning(
                    "[Service] retaining ambiguous task attachment setup %s for reconciliation",
                    task.id,
                )
                raise
            task = committed
        try:
            self._register_to_scheduler(task, honor_run_on_start=True)
        except Exception:
            self._unregister_managed_task(task.id)
            try:
                if fence is None:
                    await storage.delete_task(task.id)
                else:
                    deleted_task = await storage.mark_task_attachment_deletion(
                        task.id,
                        fence=fence,
                    )
                    if deleted_task is not None:
                        await self._release_pending_attachment_references(
                            deleted_task,
                            fence,
                        )
            except Exception:
                logger.exception(
                    "[Service] failed to finish attachment cleanup after registration failure %s",
                    task.id,
                )
            raise

        logger.info(
            "[Service] created task %s agent=%s trigger=%s",
            task.id,
            request.agent_id,
            request.trigger_type.value,
        )
        return task

    async def update_task(
        self, task_id: str, request: ScheduledTaskUpdate
    ) -> Optional[ScheduledTask]:
        """Update task fields and refresh the scheduler registration."""
        if "input_payload" in request.model_dump(exclude_unset=True):
            async with _attachment_mutation(task_id) as token:
                storage = get_scheduled_task_storage()
                owned_task = await storage.claim_attachment_mutation(task_id, token)
                if owned_task is None:
                    return None
                fence = _attachment_fence(owned_task, token)
                return await self._update_task(
                    task_id,
                    request,
                    attachment_task=owned_task,
                    fence=fence,
                )
        return await self._update_task(task_id, request)

    async def _update_task(
        self,
        task_id: str,
        request: ScheduledTaskUpdate,
        *,
        attachment_task: ScheduledTask | None = None,
        fence: AttachmentMutationFence | None = None,
    ) -> Optional[ScheduledTask]:
        storage = get_scheduled_task_storage()
        task = attachment_task or await storage.get_task(task_id)
        if task is None or task.status == ScheduledTaskStatus.DELETED:
            return None

        updates: dict[str, Any] = request.model_dump(exclude_unset=True)

        # Validate trigger changes as one atomic pair. This also supports changing
        # trigger_type and trigger_config in a single update request.
        if "trigger_type" in updates or "trigger_config" in updates or "timezone" in updates:
            trigger_type = updates.get("trigger_type", task.trigger_type)
            trigger_config = updates.get("trigger_config", task.trigger_config)
            timezone_name = updates.get("timezone", task.timezone)
            self._build_trigger(trigger_type, trigger_config, timezone_name)
            if trigger_type == TriggerType.DATE:
                updates["run_on_start"] = False

        if not updates:
            return task

        attachment_update = "input_payload" in updates
        if attachment_update:
            if fence is None:
                raise RuntimeError("Attachment update requires a mutation fence")
            attachment_keys = _task_attachment_keys(updates["input_payload"])
            live_keys = set(task.attachment_keys)
            added_keys = [key for key in attachment_keys if key not in live_keys]
            staged = await storage.stage_attachment_claim(
                task_id,
                added_keys,
                fence=fence,
            )
            if staged is None:
                return None
            file_records = FileRecordStorage()
            await file_records.claim_scheduled_task_references(
                added_keys,
                task.owner_id,
                task.id,
                mutation_generation=fence.generation,
            )
            try:
                updated_task = await storage.commit_attachment_update(
                    task_id,
                    updates,
                    attachment_keys,
                    fence=fence,
                )
            except (Exception, asyncio.CancelledError):
                # Cancellation can mean this owner lost its mutation lock, and a
                # Mongo exception can mean the commit applied without a reply.
                # In either case the task UUID is not a safe compensation token:
                # a successor may already have adopted the same file lease.
                # Leave the durable claim marker for the current owner/reconciler.
                logger.warning(
                    "[Service] retaining ambiguous attachment update %s for reconciliation",
                    task.id,
                )
                raise
            if updated_task is None:
                logger.warning(
                    "[Service] retaining missing attachment update %s for reconciliation",
                    task.id,
                )
                return None
        else:
            await storage.update_task(task_id, updates)
            updated_task = await storage.get_task(task_id)
            if updated_task is None:
                return None

        # Refresh scheduler registration
        if updated_task.enabled and updated_task.status == ScheduledTaskStatus.ACTIVE:
            self._register_to_scheduler(updated_task)
        else:
            self._unregister_managed_task(task_id)

        if attachment_update:
            if fence is None:
                raise RuntimeError("Attachment update requires a mutation fence")
            await self._release_pending_attachment_references(updated_task, fence)

        return updated_task

    async def pause_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Pause a task — remove from scheduler but keep the DB record."""
        storage = get_scheduled_task_storage()
        task = await storage.get_task(task_id)
        if task is None or task.status == ScheduledTaskStatus.DELETED:
            return None
        await storage.update_task(task_id, {"status": ScheduledTaskStatus.PAUSED, "enabled": False})
        self._unregister_managed_task(task_id)
        logger.info("[Service] paused task %s", task_id)
        return await storage.get_task(task_id)

    async def resume_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Resume a paused task — re-register with the scheduler."""
        storage = get_scheduled_task_storage()
        task = await storage.get_task(task_id)
        if task is None or task.status == ScheduledTaskStatus.DELETED:
            return None
        await storage.update_task(task_id, {"status": ScheduledTaskStatus.ACTIVE, "enabled": True})
        updated = await storage.get_task(task_id)
        if updated is not None:
            self._register_to_scheduler(updated)
        logger.info("[Service] resumed task %s", task_id)
        return updated

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task after durably recording attachment releases."""
        async with _attachment_mutation(task_id) as token:
            storage = get_scheduled_task_storage()
            task = await storage.claim_attachment_mutation(task_id, token)
            if task is None:
                return False
            fence = _attachment_fence(task, token)
            return await self._delete_task(storage, task, fence)

    async def _delete_task(
        self,
        storage: Any,
        task: ScheduledTask,
        fence: AttachmentMutationFence,
    ) -> bool:
        self._unregister_managed_task(task.id)
        deleted_task = await storage.mark_task_attachment_deletion(
            task.id,
            fence=fence,
        )
        if deleted_task is None:
            return False
        await self._release_pending_attachment_references(deleted_task, fence)
        logger.info("[Service] deleted task %s", task.id)
        return True

    async def reconcile_attachment_references(self) -> int:
        """Finish durable attachment transitions left by crashes or old definitions."""
        storage = get_scheduled_task_storage()
        tasks = await storage.list_attachment_reconciliation_tasks()
        reconciled = 0
        for listed_task in tasks:
            async with _attachment_mutation(listed_task.id) as token:
                task = await storage.claim_attachment_mutation(listed_task.id, token)
                if task is None:
                    continue
                fence = _attachment_fence(task, token)
                await self._reconcile_attachment_task(storage, task, fence)
                reconciled += 1
        return reconciled

    async def _reconcile_attachment_task(
        self,
        storage: Any,
        task: ScheduledTask,
        fence: AttachmentMutationFence,
    ) -> None:
        if task.attachment_setup_pending:
            deleted_task = await storage.mark_task_attachment_deletion(
                task.id,
                fence=fence,
            )
            if deleted_task is not None:
                await self._release_pending_attachment_references(deleted_task, fence)
            return

        pending_claims = list(task.pending_attachment_claim_keys)
        if pending_claims:
            live_keys = set(task.attachment_keys)
            file_records = FileRecordStorage()
            for offset in range(0, len(pending_claims), REFERENCE_KEYS_MAX):
                chunk = pending_claims[offset : offset + REFERENCE_KEYS_MAX]
                rollback_keys = [key for key in chunk if key not in live_keys]
                if rollback_keys:
                    await file_records.adopt_scheduled_task_reference_generation(
                        rollback_keys,
                        task.owner_id,
                        task.id,
                        mutation_generation=fence.generation,
                    )
                    await file_records.release_scheduled_task_references(
                        rollback_keys,
                        task.owner_id,
                        task.id,
                        mutation_generation=fence.generation,
                    )
                cleared = await storage.clear_pending_attachment_claims(
                    task.id,
                    chunk,
                    fence=fence,
                )
                if not cleared:
                    raise RuntimeError(
                        f"Scheduled task attachment mutation fence was lost for {task.id}"
                    )
            task = task.model_copy(update={"pending_attachment_claim_keys": []})

        if task.status == ScheduledTaskStatus.DELETED:
            await self._release_pending_attachment_references(task, fence)
            return

        desired_keys = _task_attachment_keys(task.input_payload)
        if desired_keys != task.attachment_keys:
            live_keys = set(task.attachment_keys)
            added_keys = [key for key in desired_keys if key not in live_keys]
            if added_keys:
                staged = await storage.stage_attachment_claim(
                    task.id,
                    added_keys,
                    fence=fence,
                )
                if staged is None:
                    raise RuntimeError(
                        f"Scheduled task {task.id} disappeared during attachment recovery"
                    )
                await FileRecordStorage().claim_scheduled_task_references(
                    added_keys,
                    task.owner_id,
                    task.id,
                    mutation_generation=fence.generation,
                )
            try:
                committed = await storage.commit_attachment_update(
                    task.id,
                    {},
                    desired_keys,
                    fence=fence,
                )
                if committed is None:
                    raise RuntimeError(
                        f"Scheduled task {task.id} disappeared during attachment recovery"
                    )
            except (Exception, asyncio.CancelledError):
                # Preserve the durable marker and token when commit ownership is
                # uncertain. A later serialized reconciliation can distinguish
                # a live attachment from a truly uncommitted claim.
                logger.warning(
                    "[Service] retaining ambiguous attachment recovery %s",
                    task.id,
                )
                raise
            task = committed

        await self._release_pending_attachment_references(task, fence)

    async def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        return await get_scheduled_task_storage().get_task(task_id)

    async def list_tasks(
        self,
        owner_id: Optional[str] = None,
        status: Optional[ScheduledTaskStatus] = None,
    ) -> list[ScheduledTask]:
        return await get_scheduled_task_storage().list_tasks(owner_id=owner_id, status=status)

    async def list_tasks_paginated(
        self,
        owner_id: str,
        status: Optional[ScheduledTaskStatus] = None,
        source_session_id: Optional[str] = None,
        created_by: Optional[str] = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list[ScheduledTaskResponse], int]:
        """List tasks with pagination, scoped by owner_id."""
        storage = get_scheduled_task_storage()
        tasks, total = await storage.list_tasks_paginated(
            owner_id=owner_id,
            status=status,
            source_session_id=source_session_id,
            created_by=created_by,
            skip=skip,
            limit=limit,
        )
        unread_counts = await SessionStorage().get_unread_counts_for_scheduled_tasks(
            user_id=owner_id,
            scheduled_task_ids=[task.id for task in tasks],
        )
        responses = [self.to_response(t, unread_count=unread_counts.get(t.id, 0)) for t in tasks]
        return responses, total

    async def get_task_response(self, task: ScheduledTask) -> ScheduledTaskResponse:
        """Convert a task to an API response with unread session totals."""
        unread_counts = await SessionStorage().get_unread_counts_for_scheduled_tasks(
            user_id=task.owner_id,
            scheduled_task_ids=[task.id],
        )
        return self.to_response(task, unread_count=unread_counts.get(task.id, 0))

    # ── Execution ──────────────────────────────────

    async def run_task_now(self, task_id: str) -> dict:
        """Manually trigger a task execution."""
        runner = get_scheduled_task_runner()
        return await runner.run(task_id, trigger_type="manual")

    async def get_task_runs(
        self, task_id: str, limit: int = 20, offset: int = 0
    ) -> tuple[list[TaskRunResponse], int]:
        storage = get_scheduled_task_storage()
        records, total = await storage.list_runs(task_id, limit, offset)
        responses = [
            TaskRunResponse(
                id=r.id,
                task_id=r.task_id,
                agent_id=r.agent_id,
                trigger_type=r.trigger_type,
                status=r.status,
                session_id=r.session_id,
                trace_id=r.trace_id,
                input_snapshot=r.input_snapshot,
                output_result=r.output_result,
                error_message=r.error_message,
                retry_count=r.retry_count,
                started_at=r.started_at,
                finished_at=r.finished_at,
                duration_ms=r.duration_ms,
                created_at=r.created_at,
            )
            for r in records
        ]
        return responses, total

    # ── Startup ────────────────────────────────────

    async def load_persisted_tasks(self) -> int:
        """Load all active tasks from DB and register them with the scheduler.

        Called once during process startup.
        """
        storage = get_scheduled_task_storage()
        marker = await storage.get_active_tasks_marker()
        if self._active_tasks_marker == marker:
            logger.debug("[Service] scheduled tasks unchanged; skipped scheduler reload")
            return self._active_task_count

        tasks = await storage.list_active_tasks()
        now = utc_now()
        active_task_ids: set[str] = set()
        for task in tasks:
            if self._is_expired_date_task(task, now):
                await storage.update_task(
                    task.id,
                    {"status": ScheduledTaskStatus.PAUSED, "enabled": False},
                )
                self._unregister_managed_task(task.id)
                continue
            active_task_ids.add(task.id)
            self._register_to_scheduler(task)

        for task_id in set(_managed_task_signatures) - active_task_ids:
            self._unregister_managed_task(task_id)

        self._active_tasks_marker = marker
        self._active_task_count = len(active_task_ids)
        logger.info("[Service] loaded %d persisted tasks into scheduler", len(tasks))
        return len(tasks)

    # ── Conversion helpers ─────────────────────────

    @staticmethod
    def to_response(
        task: ScheduledTask,
        unread_count: int = 0,
    ) -> ScheduledTaskResponse:
        """Convert a ScheduledTask model to an API response."""
        return ScheduledTaskResponse(
            id=task.id,
            name=task.name,
            description=task.description,
            agent_id=task.agent_id,
            trigger_type=task.trigger_type,
            trigger_config=task.trigger_config,
            timezone=task.timezone,
            input_payload=task.input_payload,
            status=task.status,
            enabled=task.enabled,
            run_on_start=task.run_on_start,
            max_retries=task.max_retries,
            timeout_seconds=task.timeout_seconds,
            owner_id=task.owner_id,
            source_session_id=task.source_session_id,
            source_run_id=task.source_run_id,
            created_by=task.created_by,
            delivery=task.delivery,
            last_run_at=task.last_run_at,
            last_run_status=task.last_run_status,
            last_run_id=task.last_run_id,
            total_runs=task.total_runs,
            unread_count=unread_count,
            created_at=task.created_at,
            updated_at=task.updated_at,
        )

    # ── Internal ───────────────────────────────────

    async def _release_pending_attachment_references(
        self,
        task: ScheduledTask,
        fence: AttachmentMutationFence,
    ) -> int:
        """Release only durable pending keys that are not live in the definition."""
        live_keys = set(task.attachment_keys)
        pending_keys = [
            key for key in task.pending_attachment_release_keys if key not in live_keys
        ]
        storage = get_scheduled_task_storage()
        released = 0
        file_records = FileRecordStorage()
        for offset in range(0, len(pending_keys), REFERENCE_KEYS_MAX):
            chunk = pending_keys[offset : offset + REFERENCE_KEYS_MAX]
            await file_records.adopt_scheduled_task_reference_generation(
                chunk,
                task.owner_id,
                task.id,
                mutation_generation=fence.generation,
            )
            await file_records.release_scheduled_task_references(
                chunk,
                task.owner_id,
                task.id,
                mutation_generation=fence.generation,
            )
            cleared = await storage.clear_pending_attachment_releases(
                task.id,
                chunk,
                fence=fence,
            )
            if not cleared:
                raise RuntimeError(
                    f"Scheduled task attachment mutation fence was lost for {task.id}"
                )
            released += len(chunk)
        if task.status == ScheduledTaskStatus.DELETED:
            await storage.finalize_deleted_task(task.id, fence=fence)
        return released

    def _register_to_scheduler(
        self,
        task: ScheduledTask,
        *,
        honor_run_on_start: bool = False,
    ) -> None:
        """Register a persisted task with the in-process APScheduler."""
        signature = self._scheduler_signature(task)
        scheduler = get_runtime_scheduler()
        if _managed_task_signatures.get(task.id) == signature and scheduler.has_job(task.id):
            return

        trigger = self._build_task_trigger(task)
        runner = get_scheduled_task_runner()
        task_id = task.id
        trigger_type_value = task.trigger_type.value

        # Capture task.id via default arg to avoid late-binding issues
        job = ScheduledJob(
            id=task_id,
            name=task.name,
            trigger=trigger,
            handler=lambda: runner.run(task_id, trigger_type=trigger_type_value),
            enabled=task.enabled,
            run_on_start=bool(honor_run_on_start and task.run_on_start),
            max_instances=1,
            coalesce=True,
        )
        scheduler.register_job(job)
        _managed_task_signatures[task_id] = signature

    @staticmethod
    def _unregister_managed_task(task_id: str) -> None:
        get_runtime_scheduler().unregister_job(task_id)
        _managed_task_signatures.pop(task_id, None)

    @staticmethod
    def _scheduler_signature(task: ScheduledTask) -> str:
        return json.dumps(
            {
                "trigger_type": task.trigger_type.value,
                "trigger_config": task.trigger_config,
                "timezone": task.timezone,
                "enabled": task.enabled,
                "status": task.status.value,
                "run_on_start": task.run_on_start,
                "name": task.name,
                "last_run_at": task.last_run_at,
                "created_at": task.created_at,
            },
            default=str,
            sort_keys=True,
        )

    @staticmethod
    def _build_task_trigger(task: ScheduledTask) -> BaseTrigger:
        """Build a trigger for a concrete persisted task.

        Interval tasks are anchored to persisted timestamps so multiple
        processes compute the same future fire times instead of drifting from
        each process startup time.
        """
        if task.trigger_type == TriggerType.INTERVAL:
            interval_cfg = IntervalTriggerConfig(**task.trigger_config)
            anchor = task.last_run_at or task.created_at
            start_date = (
                ensure_utc(anchor) + timedelta(seconds=interval_cfg.seconds)
                if anchor is not None
                else None
            )
            return IntervalTrigger(
                seconds=interval_cfg.seconds,
                start_date=start_date,
                timezone=_coerce_timezone(task.timezone),
            )
        return ScheduledTaskService._build_trigger(
            task.trigger_type,
            task.trigger_config,
            task.timezone,
        )

    @staticmethod
    def _build_trigger(
        trigger_type: TriggerType,
        config: dict,
        timezone_name: str | None = "UTC",
    ) -> BaseTrigger:
        """Build an APScheduler trigger from the stored config dict."""
        tz = _coerce_timezone(timezone_name)
        if trigger_type == TriggerType.INTERVAL:
            interval_cfg = IntervalTriggerConfig(**config)
            return IntervalTrigger(seconds=interval_cfg.seconds, timezone=tz)
        if trigger_type == TriggerType.CRON:
            cron_cfg = CronTriggerConfig(**config)
            return CronTrigger(
                year=cron_cfg.year,
                month=cron_cfg.month,
                day=cron_cfg.day,
                week=cron_cfg.week,
                day_of_week=cron_cfg.day_of_week,
                hour=cron_cfg.hour,
                minute=cron_cfg.minute,
                second=cron_cfg.second,
                timezone=tz,
            )
        if trigger_type == TriggerType.DATE:
            date_cfg = DateTriggerConfig(**config)
            run_date = _ensure_utc_in_timezone(date_cfg.run_date, timezone_name)
            if run_date <= utc_now():
                raise ValueError("date trigger run_date must be in the future")
            return DateTrigger(run_date=run_date, timezone="UTC")
        raise ValueError(f"Unsupported trigger type: {trigger_type}")

    @staticmethod
    def _is_expired_date_task(task: ScheduledTask, now=None) -> bool:
        if task.trigger_type != TriggerType.DATE:
            return False
        try:
            cfg = DateTriggerConfig(**task.trigger_config)
        except Exception:
            return False
        return _ensure_utc_in_timezone(cfg.run_date, task.timezone) <= (now or utc_now())
