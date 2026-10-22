from __future__ import annotations

from typing import Any

from src.infra.logging import get_logger
from src.infra.session.trace_storage import get_trace_storage

from .status import TaskStatus

logger = get_logger(__name__)


async def is_active_stale_trace(trace: dict[str, Any], run_id: str, metadata: dict) -> bool:
    """Only a stale-cleanup error can be contradicted by live execution evidence."""
    if (
        trace.get("status") != "error"
        or (trace.get("metadata") or {}).get("error_code") != "stale_run_recovery"
    ):
        return False
    if metadata.get("current_run_id") == run_id:
        status = metadata.get("task_status")
        if status == TaskStatus.WAITING_HUMAN.value:
            return True
        if status in {"completed", "failed", "error", "cancelled", "expired"}:
            return False
    from .heartbeat import TaskHeartbeat

    return not await TaskHeartbeat().is_stale(run_id)


def is_recoverable_restart(metadata: dict[str, Any], run_id: str | None) -> bool:
    return (
        bool(run_id)
        and metadata.get("current_run_id") == run_id
        and metadata.get("task_status") == TaskStatus.FAILED.value
        and metadata.get("task_recoverable") is True
        and metadata.get("task_error_code") == "server_restart"
    )


class TaskStatusQueries:
    """Read task status and error details from storage backends."""

    def __init__(self, *, storage: Any, run_info: dict[str, dict[str, Any]]) -> None:
        self._storage = storage
        self._run_info = run_info

    async def load_session_record(self, raw_session: dict[str, Any]) -> Any | None:
        """Load a normalized session model from a raw MongoDB session document."""
        session_id = raw_session.get("session_id") or str(raw_session.get("_id"))
        session = await self._storage.get_by_session_id(session_id)
        if session is not None:
            return session
        return await self._storage.get_by_id(session_id)

    async def get_status(self, session_id: str) -> TaskStatus:
        """Get the current task status for a session."""
        try:
            session = await self._storage.get_by_session_id(session_id)
            if session and session.metadata:
                run_id = session.metadata.get("current_run_id")
                if isinstance(run_id, str) and is_recoverable_restart(session.metadata, run_id):
                    return await self.get_run_status(session_id, run_id)
                task_status = session.metadata.get("task_status")
                if task_status:
                    return TaskStatus(task_status)
        except Exception as e:
            logger.warning("Failed to get status from session storage: %s", e)
        return TaskStatus.PENDING

    async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
        """Get status for a specific run."""
        fallback_status = TaskStatus.PENDING
        metadata: dict[str, Any] = {}
        try:
            session = await self._storage.get_by_session_id(session_id)
            metadata = getattr(session, "metadata", None) or {}
            if session and session.metadata and session.metadata.get("current_run_id") == run_id:
                task_status = session.metadata.get("task_status")
                if task_status:
                    if not is_recoverable_restart(session.metadata, run_id):
                        return TaskStatus(task_status)
                    # A finished trace takes precedence over stale restart metadata.
                    fallback_status = TaskStatus.RECOVERING
        except Exception as e:
            logger.warning("Failed to get run status from session storage: %s", e)

        try:
            trace_storage = get_trace_storage()
            cursor = (
                trace_storage.collection.find(
                    {"run_id": run_id}, {"status": 1, "metadata.error_code": 1, "_id": 0}
                )
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                if await is_active_stale_trace(traces[0], run_id, metadata):
                    return TaskStatus.RUNNING
                trace_status = traces[0].get("status")
                if trace_status:
                    status_map = {
                        "running": TaskStatus.RUNNING,
                        "completed": TaskStatus.COMPLETED,
                        "error": TaskStatus.FAILED,
                        "failed": TaskStatus.FAILED,
                        "cancelled": TaskStatus.CANCELLED,
                        "expired": TaskStatus.EXPIRED,
                        "waiting_human": TaskStatus.WAITING_HUMAN,
                    }
                    if fallback_status != TaskStatus.RECOVERING or trace_status in {
                        "completed",
                        "error",
                        "failed",
                        "cancelled",
                        "expired",
                    }:
                        return status_map.get(trace_status, TaskStatus.PENDING)
        except Exception as e:
            logger.warning("Failed to get run status from trace storage: %s", e)

        return fallback_status

    async def get_error(self, session_id: str) -> str | None:
        """Get the latest task error for a session."""
        try:
            session = await self._storage.get_by_session_id(session_id)
            if session and session.metadata:
                return session.metadata.get("task_error")
        except Exception as e:
            logger.warning("Failed to get error from session storage: %s", e)
        return None

    async def get_run_error(self, run_id: str) -> str | None:
        """Get error details for a specific run."""
        try:
            trace_storage = get_trace_storage()
            cursor = (
                trace_storage.collection.find(
                    {"run_id": run_id}, {"metadata": 1, "trace_id": 1, "_id": 0}
                )
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                trace = traces[0]
                metadata = trace.get("metadata", {})
                if metadata.get("error"):
                    return metadata.get("error")
                trace_id = trace.get("trace_id") or self.get_trace_id(run_id)
                if trace_id:
                    get_last_trace_event = getattr(trace_storage, "get_last_trace_event", None)
                    if get_last_trace_event is None:
                        get_last_trace_event = trace_storage.get_first_trace_event
                    event = await get_last_trace_event(trace_id, ["error"])
                    if event:
                        data = event.get("data", {})
                        return data.get("error")
        except Exception as e:
            logger.warning("Failed to get run error from trace storage: %s", e)

        run_info = self._run_info.get(run_id)
        if run_info:
            session_id = run_info.get("session_id")
            if session_id:
                try:
                    session = await self._storage.get_by_session_id(session_id)
                    if session and session.metadata:
                        return session.metadata.get("task_error")
                except Exception as e:
                    logger.warning("Failed to get run error from session storage: %s", e)

        return None

    async def lookup_trace_id_for_run(self, run_id: str) -> str | None:
        try:
            from src.infra.session.trace_storage import get_trace_storage

            trace_storage = get_trace_storage()
            cursor = (
                trace_storage.collection.find({"run_id": run_id}, {"trace_id": 1, "_id": 0})
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                trace_id = traces[0].get("trace_id")
                return str(trace_id) if trace_id else None
        except Exception as e:
            logger.warning("Failed to lookup trace_id for run %s: %s", run_id, e)
        return None

    def get_trace_id(self, run_id: str) -> str | None:
        """Get the trace identifier associated with a run."""
        info = self._run_info.get(run_id)
        return info.get("trace_id") if info else None
