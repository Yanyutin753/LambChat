"""Best-effort quota refresh events shared by single and bulk mutations."""

import asyncio

from src.infra.logging import get_logger

logger = get_logger(__name__)


async def broadcast_quota_changed(user_id: str) -> None:
    try:
        from src.infra.websocket import get_connection_manager

        async with asyncio.timeout(2):
            await get_connection_manager().send_to_user_with_broadcast(
                user_id, {"type": "usage_quota_updated"}
            )
    except Exception:
        logger.debug("Failed to broadcast quota update", exc_info=True)
