"""Unambiguous tenant-scoped channel session identities."""

import hashlib
import json
import uuid


def channel_session_scope(user_id: str, instance_id: str | None, chat_id: str) -> str:
    """Hash the full identity; never reuse legacy chat-only session mappings."""
    identity = json.dumps(
        [user_id, instance_id, chat_id], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


async def new_delivery_session(prefix: str) -> str:
    """Persist /new's chosen identity before changing the conversation pointer."""
    from src.infra.channel.inbox_worker import current_delivery

    context = current_delivery.get()
    if context and context.checkpoint.get("new_session_id"):
        return str(context.checkpoint["new_session_id"])
    session_id = f"{prefix}_{uuid.uuid4().hex}"
    if context:
        await context.save(new_session_id=session_id)
    return session_id
