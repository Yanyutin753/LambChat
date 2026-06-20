"""Business logic for scheduled task CRUD and scheduler coordination.

This service is the bridge between the API layer and the lower-level
storage, runner, and scheduler components.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any, Optional
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.infra.extensions import get_plugin_settings_service
from src.infra.extensions.scoped_options import (
    plugin_options_with_settings,
    sync_plugin_options_to_settings,
)
from src.infra.logging import get_logger
from src.infra.scheduler.runner import get_scheduled_task_runner
from src.infra.scheduler.runtime import ScheduledJob, get_runtime_scheduler
from src.infra.scheduler.storage import get_scheduled_task_storage
from src.infra.session.storage import SessionStorage
from src.infra.utils.datetime import ensure_utc, utc_now
from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS, PluginRuntime
from src.kernel.extensions.plugin_options import (
    declared_plugin_options_from_metadata,
    plugin_options_from_metadata,
)
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


def _ensure_agent_executable(agent_id: str) -> None:
    from src.agents import ensure_agent_executable

    ensure_agent_executable(agent_id)


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
        self.plugin_runtime: PluginRuntime | None = None
        self.plugin_settings_service = get_plugin_settings_service()

    def _runtime(self) -> PluginRuntime:
        return self.plugin_runtime or PluginRuntime(
            BUILTIN_PLUGIN_MANIFESTS,
            core_dependencies=("skill_core",),
        )

    def _declared_scheduled_task_input_payload(
        self,
        input_payload: dict,
        *,
        agent_id: str | None = None,
    ) -> dict:
        payload = dict(input_payload or {})
        plugin_options = declared_plugin_options_from_metadata(
            self._runtime(),
            payload,
            scope="scheduled_task",
            agent_id=agent_id,
        )
        if plugin_options:
            payload["plugin_options"] = plugin_options
        else:
            payload.pop("plugin_options", None)
        return payload

    # ── CRUD ───────────────────────────────────────

    async def create_task(
        self,
        request: ScheduledTaskCreate,
        owner_id: str,
    ) -> ScheduledTask:
        """Validate, persist, and register a new scheduled task."""
        # Validate trigger config
        self._build_trigger(request.trigger_type, request.trigger_config, request.timezone)
        _ensure_agent_executable(request.agent_id)

        now = utc_now()
        task_id = str(uuid4())
        input_payload = self._declared_scheduled_task_input_payload(
            request.input_payload,
            agent_id=request.agent_id,
        )
        task = ScheduledTask.model_validate(
            {
                "_id": task_id,
                "name": request.name,
                "description": request.description,
                "agent_id": request.agent_id,
                "trigger_type": request.trigger_type,
                "trigger_config": request.trigger_config,
                "timezone": request.timezone,
                "input_payload": input_payload,
                "status": ScheduledTaskStatus.ACTIVE,
                "enabled": request.enabled,
                "run_on_start": False
                if request.trigger_type == TriggerType.DATE
                else request.run_on_start,
                "max_retries": request.max_retries,
                "timeout_seconds": request.timeout_seconds,
                "owner_id": owner_id,
                "source_session_id": request.source_session_id,
                "source_run_id": request.source_run_id,
                "created_by": request.created_by,
                "delivery": request.delivery,
                "created_at": now,
                "updated_at": now,
            }
        )

        storage = get_scheduled_task_storage()
        await storage.create_task(task)
        await self._sync_scheduled_task_plugin_options(task, updated_by=owner_id)
        self._register_to_scheduler(task, honor_run_on_start=True)

        logger.info(
            "[Service] created task %s agent=%s trigger=%s",
            task_id,
            request.agent_id,
            request.trigger_type.value,
        )
        return task

    async def update_task(
        self, task_id: str, request: ScheduledTaskUpdate
    ) -> Optional[ScheduledTask]:
        """Update task fields and refresh the scheduler registration."""
        storage = get_scheduled_task_storage()
        task = await storage.get_task(task_id)
        if task is None:
            return None

        updates: dict[str, Any] = request.model_dump(exclude_unset=True)

        if "agent_id" in updates:
            _ensure_agent_executable(updates["agent_id"])

        if "input_payload" in updates:
            agent_id = updates.get("agent_id", task.agent_id)
            updates["input_payload"] = self._declared_scheduled_task_input_payload(
                updates["input_payload"],
                agent_id=agent_id,
            )

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

        await storage.update_task(task_id, updates)
        updated_task = await storage.get_task(task_id)
        if updated_task is None:
            return None
        if "input_payload" in updates:
            await self._sync_scheduled_task_plugin_options(
                updated_task,
                updated_by=updated_task.owner_id,
            )

        # Refresh scheduler registration
        if updated_task.enabled and updated_task.status == ScheduledTaskStatus.ACTIVE:
            self._register_to_scheduler(updated_task)
        else:
            self._unregister_managed_task(task_id)

        return updated_task

    async def pause_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Pause a task — remove from scheduler but keep the DB record."""
        storage = get_scheduled_task_storage()
        task = await storage.get_task(task_id)
        if task is None:
            return None
        await storage.update_task(task_id, {"status": ScheduledTaskStatus.PAUSED, "enabled": False})
        self._unregister_managed_task(task_id)
        logger.info("[Service] paused task %s", task_id)
        return await storage.get_task(task_id)

    async def resume_task(self, task_id: str) -> Optional[ScheduledTask]:
        """Resume a paused task — re-register with the scheduler."""
        storage = get_scheduled_task_storage()
        task = await storage.get_task(task_id)
        if task is None:
            return None
        await storage.update_task(task_id, {"status": ScheduledTaskStatus.ACTIVE, "enabled": True})
        updated = await storage.get_task(task_id)
        if updated is not None:
            self._register_to_scheduler(updated)
        logger.info("[Service] resumed task %s", task_id)
        return updated

    async def delete_task(self, task_id: str) -> bool:
        """Physically delete a task."""
        self._unregister_managed_task(task_id)
        storage = get_scheduled_task_storage()
        deleted = await storage.delete_task(task_id)
        if deleted:
            logger.info("[Service] deleted task %s", task_id)
        return deleted

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
        responses = [
            await self.to_response_with_plugin_settings(
                task,
                unread_count=unread_counts.get(task.id, 0),
            )
            for task in tasks
        ]
        return responses, total

    async def get_task_response(self, task: ScheduledTask) -> ScheduledTaskResponse:
        """Convert a task to an API response with unread session totals."""
        unread_counts = await SessionStorage().get_unread_counts_for_scheduled_tasks(
            user_id=task.owner_id,
            scheduled_task_ids=[task.id],
        )
        return await self.to_response_with_plugin_settings(
            task,
            unread_count=unread_counts.get(task.id, 0),
        )

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

    async def to_response_with_plugin_settings(
        self,
        task: ScheduledTask,
        unread_count: int = 0,
    ) -> ScheduledTaskResponse:
        response = self.to_response(task, unread_count=unread_count)
        plugin_options = await plugin_options_with_settings(
            runtime=self._runtime(),
            service=self.plugin_settings_service,
            scope="scheduled_task",
            subject_id=task.id,
            plugin_options=plugin_options_from_metadata(task.input_payload),
        )
        if plugin_options:
            response.input_payload = {
                **response.input_payload,
                "plugin_options": plugin_options,
            }
        return response

    async def _sync_scheduled_task_plugin_options(
        self,
        task: ScheduledTask,
        *,
        updated_by: str | None,
    ) -> None:
        await sync_plugin_options_to_settings(
            runtime=self._runtime(),
            service=self.plugin_settings_service,
            scope="scheduled_task",
            subject_id=task.id,
            plugin_options=plugin_options_from_metadata(task.input_payload),
            updated_by=updated_by,
        )

    # ── Internal ───────────────────────────────────

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
