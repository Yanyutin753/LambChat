"""scheduled_task_list and scheduled_task_get tool implementations."""

import sys
from typing import TYPE_CHECKING, Annotated, Any, Literal, Optional

from langchain_core.tools import InjectedToolArg

from src.infra.scheduler.service import ScheduledTaskService
from src.infra.tool.backend_utils import get_user_id_from_runtime
from src.kernel.schemas.scheduled_task import ScheduledTaskStatus
from src.kernel.types import Permission

if TYPE_CHECKING:
    from langchain.tools import ToolRuntime
else:
    try:
        from langchain.tools import ToolRuntime  # type: ignore[assignment]
    except ImportError:  # pragma: no cover
        _mod = type(sys)("langchain.tools")  # type: ignore[assignment]
        _mod.ToolRuntime = Any  # type: ignore[assignment]
        sys.modules.setdefault("langchain.tools", _mod)
        from langchain.tools import ToolRuntime  # type: ignore[assignment]

from langchain.tools import tool  # noqa: E402

from src.infra.tool.scheduled_task.helpers import _json, _permission_error


@tool
async def scheduled_task_list(
    task_id: Annotated[
        str | None,
        "Task ID for one detailed result; omit to list.",
    ] = None,
    status: Annotated[
        Literal["active", "paused", "deleted"] | None,
        "Optional status filter.",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """List the user's scheduled tasks, optionally by status, or fetch task_id details."""
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return _json({"error": "No user context available"})
    error = await _permission_error(user_id, Permission.SCHEDULED_TASK_READ.value)
    if error:
        return _json(error)

    service = ScheduledTaskService()
    if task_id:
        try:
            task = await service.get_task(task_id)
        except Exception as e:
            return _json({"error": f"Failed to get task: {e}"})

        if task is None or task.owner_id != user_id:
            return _json({"error": f"Task '{task_id}' not found"})

        resp = ScheduledTaskService.to_response(task)
        return _json(
            {
                "success": True,
                "task": resp.model_dump(mode="json"),
            }
        )

    status_enum: Optional[ScheduledTaskStatus] = None
    if status:
        try:
            status_enum = ScheduledTaskStatus(status)
        except ValueError:
            return _json(
                {"error": f"Invalid status '{status}'. Use 'active', 'paused', or 'deleted'."}
            )

    try:
        tasks = await service.list_tasks(owner_id=user_id, status=status_enum)
    except Exception as e:
        return _json({"error": f"Failed to list tasks: {e}"})

    items = [ScheduledTaskService.to_response(t).model_dump(mode="json") for t in tasks]
    return _json(
        {
            "success": True,
            "tasks": items,
            "total": len(items),
        }
    )


@tool
async def scheduled_task_get(
    task_id: Annotated[str, "ID of the scheduled task"],
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,  # type: ignore[assignment]
) -> str:
    """Get detailed information about a specific scheduled task, including its
    last run status, total runs, and trigger configuration."""
    user_id = get_user_id_from_runtime(runtime)
    if not user_id:
        return _json({"error": "No user context available"})
    error = await _permission_error(user_id, Permission.SCHEDULED_TASK_READ.value)
    if error:
        return _json(error)

    service = ScheduledTaskService()
    try:
        task = await service.get_task(task_id)
    except Exception as e:
        return _json({"error": f"Failed to get task: {e}"})

    if task is None:
        return _json({"error": f"Task '{task_id}' not found"})

    if task.owner_id != user_id:
        return _json({"error": f"Task '{task_id}' not found"})

    resp = ScheduledTaskService.to_response(task)
    return _json(
        {
            "success": True,
            "task": resp.model_dump(mode="json"),
        }
    )
