"""Project detached provider settlements into the existing usage log."""

import asyncio

from src.infra.logging import get_logger
from src.infra.usage.storage import get_usage_storage
from src.infra.user.storage import UserStorage
from src.infra.utils.datetime import utc_now
from src.infra.websocket import get_connection_manager

logger = get_logger(__name__)


async def write_auxiliary_usage(
    reservation: dict, settlement: dict, message=None, *, status: str = "completed"
) -> None:
    """A projection failure must never replay the paid provider request."""
    try:
        context = reservation.get("context") or {}
        trace_id = f"usage_call_{reservation['id']}"
        units = settlement["charged_units"]
        complete = not settlement["unknown"]
        identity = {
            "model": context.get("model") or "",
            "model_id": context.get("model_config_id") or "",
            "provider": context.get("provider") or "",
        }
        usage = getattr(message, "usage_metadata", None) or {}
        details = usage.get("input_token_details") or {}
        counts = {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "cache_read_tokens": details.get("cache_read"),
            "cache_creation_tokens": details.get("cache_creation"),
        }
        unknown = [key for key, value in counts.items() if type(value) is not int or value < 0]
        data = {
            **{key: value if key not in unknown else 0 for key, value in counts.items()},
            "unknown_usage_fields": unknown,
            "usage_incomplete": bool(unknown),
            "input_includes_cache": type(counts["input_tokens"]) is int
            and counts["input_tokens"] >= 0
            and all(
                type(value) is int and value >= 0 for value in counts.values() if value is not None
            ),
            "cost_source": "provider_settlement",
            "cost_units": units,
            "cost_complete": complete,
            "cost_usd" if complete else "partial_cost_usd": units / 1_000_000_000,
            "model": identity["model"],
            "model_id": identity["model_id"],
            "actual_models": [identity] if any(identity.values()) else [],
        }
        username = ""
        try:
            user = await UserStorage().get_by_id(reservation["user_id"])
            if user is not None:
                username = user.username
        except Exception:
            logger.debug("Failed to resolve auxiliary usage username", exc_info=True)
        saved = await get_usage_storage().upsert_usage_log_from_trace_metadata(
            {
                "trace_id": trace_id,
                "event_revision": 2 if complete else 1,
                "session_id": context.get("session_id") or "",
                "run_id": context.get("run_id") or "",
                "user_id": reservation["user_id"],
                "started_at": reservation.get("created_at"),
                "completed_at": utc_now(),
                "status": status,
                "metadata": {"source": "auxiliary", "username": username},
            },
            data,
        )
        if saved:
            async with asyncio.timeout(2):
                await get_connection_manager().send_to_user_with_broadcast(
                    reservation["user_id"],
                    {"type": "usage:updated", "data": {"trace_id": trace_id}},
                )
    except Exception:
        logger.warning("Failed to project auxiliary usage", exc_info=True)
