"""Optional approval metadata for an already-owned session history page."""

from typing import Any

from src.infra.logging import get_logger
from src.infra.storage import mongodb
from src.kernel.schemas.user import TokenPayload

logger = get_logger(__name__)


async def prefetch_session_approval_statuses(
    events: list[dict[str, Any]], session_id: str, user: TokenPayload
) -> dict[str, dict[str, Any]] | None:
    if "chat:write" not in user.permissions:
        return None
    approval_ids = list(
        dict.fromkeys(
            event["data"]["id"]
            for event in events
            if event.get("event_type") == "approval_required"
            and isinstance(event.get("data"), dict)
            and isinstance(event["data"].get("id"), str)
            and event["data"]["id"]
        )
    )
    try:
        approvals = await mongodb.get_approval_storage().get_many(approval_ids)
        return {
            approval_id: approval.model_dump()
            if (approval := approvals.get(approval_id)) is not None
            and (
                approval.user_id == user.sub
                or (not approval.user_id and approval.session_id == session_id)
            )
            else {"id": approval_id, "status": "not_found"}
            for approval_id in approval_ids
        }
    except Exception as exc:
        logger.warning("History approval prefetch failed: %s", type(exc).__name__)
        return None
