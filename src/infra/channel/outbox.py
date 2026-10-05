"""Route connection-bound sends to whichever node owns the receiving channel."""

import asyncio
import uuid

from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.inbox import ChannelInbox
from src.kernel.schemas.channel import ChannelType


async def send_via_owner(
    user_id: str, channel_type: ChannelType, chat_id: str, content: str, instance_id: str | None
) -> bool:
    storage = ChannelStorage()
    if instance_id:
        config = await storage.get_config(user_id, channel_type, instance_id)
    else:
        configs = await storage.list_user_configs_by_type(user_id, channel_type)
        config = next((item for item in configs if item.get("enabled", True)), None)
    if not config or not config.get("enabled", True):
        return False
    instance_id = str(config.get("instance_id") or "")
    target = chat_id or str(config.get("default_chat_id") or "")
    if not target or not content.strip():
        return False
    if channel_type == ChannelType.WECOM and not config.get("receive_enabled"):
        return False
    inbox = ChannelInbox(channel_type.value, user_id, instance_id)
    key = await inbox.accept(
        {
            "message_id": "outbound:" + uuid.uuid4().hex,
            "sender_id": user_id,
            "chat_id": target,
            "content": content,
            "metadata": {},
            "outbound": True,
        }
    )
    deadline = asyncio.get_running_loop().time() + 15
    while asyncio.get_running_loop().time() < deadline:
        record = await inbox.collection.find_one(
            {"_id": key, "scope": inbox.scope_key}, {"state": 1}
        )
        if record and record.get("state") == "done":
            return True
        await asyncio.sleep(0.2)
    # Keep pending work for the owner's reconnect. False reports that delivery
    # was not confirmed within the caller's budget; it is not a deletion request.
    return False
