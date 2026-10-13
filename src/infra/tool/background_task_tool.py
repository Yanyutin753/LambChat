"""Explicit delegation that survives its originating foreground run."""

from langchain.tools import ToolRuntime, tool
from langgraph.errors import GraphBubbleUp

from src.infra.task.background_tasks import BackgroundTaskService


def create_background_task_tool(*, session_id: str, user_id: str):
    @tool
    async def start_background_task(description: str, runtime: ToolRuntime) -> dict:
        """Start independent work in a separate conversation and return immediately.
        This task continues after your foreground answer. Use for explicitly requested
        independent background work. The user receives completion notifications and can
        open the returned session to review, approve or stop it. Do not claim the work
        is complete on admission. Existing task(background=true) children remain scoped
        to your current run. Background tasks cannot recursively create detached tasks.
        execution_mode=local survives foreground completion but not a server restart;
        execution_mode=arq uses the durable worker queue."""
        configurable = runtime.config.get("configurable") or {}
        presenter = configurable.get("presenter")
        run_id = configurable.get("run_id") or getattr(presenter, "run_id", None)
        try:
            return await BackgroundTaskService().start(
                user_id=user_id,
                parent_session_id=session_id,
                parent_run_id=run_id,
                call_id=runtime.tool_call_id,
                description=description,
            )
        except GraphBubbleUp:
            raise
        except Exception:
            return {
                "status": "error",
                "error_code": "background_task_unavailable",
                "guidance": "Review the original conversation and permissions before retrying.",
            }

    return start_background_task
