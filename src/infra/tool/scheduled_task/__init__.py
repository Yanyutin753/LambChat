"""LLM-callable scheduled task tools.

Compact CRUD surface: single-task details go through scheduled_task_list(task_id=...),
lifecycle actions (pause/resume/run) through scheduled_task_update(action=...).

Split from the original monolithic scheduled_task_tool.py.
"""

from langchain_core.tools import BaseTool

from src.infra.tool.scheduled_task.create import scheduled_task_create
from src.infra.tool.scheduled_task.delete import scheduled_task_delete
from src.infra.tool.scheduled_task.read import scheduled_task_list
from src.infra.tool.scheduled_task.update import scheduled_task_update

__all__ = [
    "scheduled_task_create",
    "scheduled_task_list",
    "scheduled_task_update",
    "scheduled_task_delete",
    "get_scheduled_task_tools",
]


def get_scheduled_task_tools() -> list[BaseTool]:
    """Return scheduled task CRUD tools for the current user."""
    return [
        scheduled_task_create,
        scheduled_task_list,
        scheduled_task_update,
        scheduled_task_delete,
    ]
