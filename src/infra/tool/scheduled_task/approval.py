"""Human-in-the-loop approval flow for scheduled-task creation."""

from typing import Any

from src.infra.logging import get_logger
from src.infra.persona_preset.manager import PersonaPresetManager
from src.infra.team.manager import TeamManager

logger = get_logger(__name__)


async def create_approval(*args, **kwargs):
    from src.api.routes.human import create_approval as _create_approval

    return await _create_approval(*args, **kwargs)


async def wait_for_response(*args, **kwargs):
    from src.api.routes.human import wait_for_response as _wait_for_response

    return await _wait_for_response(*args, **kwargs)


def _format_approval_message(preview: dict[str, Any]) -> str:
    immediate = "✅ Yes" if preview["run_on_start"] else "❌ No"
    return (
        "Please confirm creation of this scheduled task.\n\n"
        "No task has been created yet. Approve to create it.\n\n"
        f"| | |\n|---|---|\n"
        f"| **Name** | {preview['name']} |\n"
        f"| **Agent** | `{preview['agent_id']}` |\n"
        f"| **Schedule** | {preview['schedule']} |\n"
        f"| **Run immediately** | {immediate} |\n"
        f"| **Timeout** | {preview['timeout_seconds']}s |\n"
        "\n"
        f"{preview['effect']}\n\n"
        "**Prompt sent on each run:**\n\n"
        f"```text\n{preview['message']}\n```"
    )


def _is_persona_admin(user) -> bool:
    return bool(user and "persona_preset:admin" in set(user.permissions or []))


def _choose_named_match(items: list[Any], query: str) -> Any | None:
    """Prefer exact name match, otherwise use the search result ranking."""
    clean_query = query.strip().casefold()
    if not clean_query or not items:
        return None
    for item in items:
        name = getattr(item, "name", "")
        if isinstance(name, str) and name.strip().casefold() == clean_query:
            return item
    return items[0]


async def _resolve_persona_preset_id_from_query(
    *,
    user_id: str,
    user,
    query: str | None,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    if not query or not query.strip():
        return None, None, None
    try:
        presets = await PersonaPresetManager().list_presets(
            user_id=user_id,
            is_admin=_is_persona_admin(user),
            q=query.strip(),
            limit=10,
        )
    except Exception as e:
        return None, None, f"Failed to search persona presets: {e}"

    match = _choose_named_match(presets, query)
    if match is None:
        return None, None, f"No persona preset matched '{query}'."
    return (
        match.id,
        {
            "id": match.id,
            "name": match.name,
            "query": query,
        },
        None,
    )


async def _resolve_team_id_from_query(
    *,
    user_id: str,
    query: str | None,
) -> tuple[str | None, dict[str, Any] | None, str | None]:
    if not query or not query.strip():
        return None, None, None
    try:
        response = await TeamManager().list_teams(
            owner_user_id=user_id,
            q=query.strip(),
            limit=10,
        )
    except Exception as e:
        return None, None, f"Failed to search teams: {e}"

    match = _choose_named_match(response.teams, query)
    if match is None:
        return None, None, f"No team matched '{query}'."
    return (
        match.id,
        {
            "id": match.id,
            "name": match.name,
            "query": query,
        },
        None,
    )


async def _send_scheduled_task_approval_event(
    *,
    approval_id: str,
    message: str,
    session_id: str | None,
    run_id: str | None,
    timeout: int,
) -> None:
    if not session_id:
        logger.warning("[ScheduledTask] Cannot send approval event: no session_id")
        return

    try:
        from src.infra.session.dual_writer import get_dual_writer

        await get_dual_writer().write_event(
            session_id=session_id,
            event_type="approval_required",
            data={
                "id": approval_id,
                "message": message,
                "type": "confirm",
                "fields": [],
                "timeout": timeout,
            },
            run_id=run_id,
        )
    except Exception as e:
        logger.error("[ScheduledTask] Failed to send approval event: %s", e, exc_info=True)


async def _confirm_scheduled_task_creation(
    *,
    preview: dict[str, Any],
    user_id: str,
    timeout: int = 300,
) -> dict[str, Any]:
    """Create a human-in-the-loop confirmation and wait for the user's decision."""
    from src.infra.logging.context import TraceContext

    ctx = TraceContext.get_request_context()

    # Unattended contexts (scheduled-task sessions use the "sch_" prefix) have
    # no interactive user to confirm. Waiting would always time out after the
    # full timeout — and MCPToolWithRetry then amplifies that to ~3x. Fail fast
    # with a clear message instead of blocking (issue #197).
    if ctx.session_id and ctx.session_id.startswith("sch_"):
        logger.info(
            "[ScheduledTask] skipping HITL confirmation in unattended session %s",
            ctx.session_id,
        )
        return {
            "approved": False,
            "status": "unattended",
            "approval_id": None,
            "message": (
                "scheduled_task_create requires interactive confirmation, which is "
                "not available in an unattended (scheduled-task) context. Create "
                "the task from an interactive chat session instead."
            ),
        }

    approval_message = _format_approval_message(preview)
    approval = await create_approval(
        message=approval_message,
        approval_type="confirm",
        fields=[],
        session_id=ctx.session_id or None,
        user_id=user_id,
        metadata={
            "approval_type": "scheduled_task_create",
            "preview": preview,
        },
    )
    await _send_scheduled_task_approval_event(
        approval_id=approval.id,
        message=approval_message,
        session_id=ctx.session_id or None,
        run_id=ctx.run_id or None,
        timeout=timeout,
    )

    response = await wait_for_response(approval.id, timeout=timeout)
    if response is None:
        return {
            "approved": False,
            "status": "timeout",
            "approval_id": approval.id,
            "message": f"Scheduled task creation timed out waiting for user confirmation ({timeout}s).",
        }
    if not response.approved:
        return {
            "approved": False,
            "status": "rejected",
            "approval_id": approval.id,
            "message": "User rejected scheduled task creation.",
        }
    return {
        "approved": True,
        "status": "approved",
        "approval_id": approval.id,
    }
