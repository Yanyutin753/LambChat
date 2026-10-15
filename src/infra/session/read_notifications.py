"""Best-effort account-wide read synchronization after persistence succeeds."""

import asyncio

from src.infra.logging import get_logger

logger = get_logger(__name__)


async def broadcast_read(user_id: str, **scope: str | None) -> None:
    # Disconnected clients reconcile from persisted state on their next fetch.
    try:
        from src.infra.websocket import get_connection_manager

        async with asyncio.timeout(2):
            await get_connection_manager().send_to_user_with_broadcast(
                user_id,
                {
                    "type": "sessions:read",
                    "data": {key: value for key, value in scope.items() if value},
                },
            )
    except Exception:
        logger.debug("Failed to broadcast session read state", exc_info=True)
