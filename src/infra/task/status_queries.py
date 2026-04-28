from __future__ import annotations

from typing import Any

from src.infra.logging import get_logger
from src.infra.session.trace_storage import get_trace_storage

from .status import TaskStatus

logger = get_logger(__name__)


class TaskStatusQueries:
    """Read task status and error details from storage backends."""

    def __init__(self, *, storage: Any, run_info: dict[str, dict[str, Any]]) -> None:
        self._storage = storage
        self._run_info = run_info

    async def get_status(self, session_id: str) -> TaskStatus:
        """Get the current task status for a session."""
        try:
            session = await self._storage.get_by_session_id(session_id)
            if session and session.metadata:
                task_status = session.metadata.get("task_status")
                if task_status:
                    return TaskStatus(task_status)
        except Exception as e:
            logger.warning("Failed to get status from session storage: %s", e)
        return TaskStatus.PENDING

    async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
        """Get status for a specific run."""
        try:
            session = await self._storage.get_by_session_id(session_id)
            if session and session.metadata:
                task_status = session.metadata.get("task_status")
                if task_status:
                    return TaskStatus(task_status)
        except Exception as e:
            logger.warning("Failed to get run status from session storage: %s", e)

        try:
            trace_storage = get_trace_storage()
            cursor = (
                trace_storage.collection.find({"run_id": run_id}, {"status": 1, "_id": 0})
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                trace_status = traces[0].get("status")
                if trace_status:
                    status_map = {
                        "running": TaskStatus.RUNNING,
                        "completed": TaskStatus.COMPLETED,
                        "error": TaskStatus.FAILED,
                    }
                    return status_map.get(trace_status, TaskStatus.PENDING)
        except Exception as e:
            logger.warning("Failed to get run status from trace storage: %s", e)

        return TaskStatus.PENDING

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
                    {"run_id": run_id}, {"metadata": 1, "events": 1, "_id": 0}
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
                events = trace.get("events", [])
                for event in reversed(events):
                    if event.get("event_type") == "error":
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

    def get_trace_id(self, run_id: str) -> str | None:
        """Get the trace identifier associated with a run."""
        info = self._run_info.get(run_id)
        return info.get("trace_id") if info else None
