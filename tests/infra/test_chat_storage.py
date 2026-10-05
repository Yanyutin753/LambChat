from unittest.mock import AsyncMock, MagicMock

from src.infra.channel.channel_storage import SENSITIVE_FIELDS, ChannelStorage
from src.kernel.schemas.channel import ChannelType


async def test_callback_instance_lookup_rejects_ambiguous_owners():
    storage = ChannelStorage()
    storage.ensure_indexes_if_needed = AsyncMock()
    collection = MagicMock()
    collection.find.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[{"user_id": "one"}, {"user_id": "two"}]
    )
    storage._collection = collection
    assert await storage.get_config_by_instance(ChannelType.WEBHOOK, "shared-id") is None
    collection.find.assert_called_once_with({"channel_type": "webhook", "instance_id": "shared-id"})
    collection.find.return_value.limit.assert_called_once_with(2)


async def test_callback_instance_lookup_preserves_authoritative_identity():
    storage = ChannelStorage()
    storage.ensure_indexes_if_needed = AsyncMock()
    collection = MagicMock()
    collection.find.return_value.limit.return_value.to_list = AsyncMock(
        return_value=[
            {
                "user_id": "owner",
                "instance_id": "instance",
                "channel_type": "webhook",
                "config": {},
            }
        ]
    )
    storage._decrypt_config = AsyncMock(
        return_value={"user_id": "spoofed", "channel_type": "feishu"}
    )
    storage._collection = collection
    config = await storage.get_config_by_instance(ChannelType.WEBHOOK, "instance")
    assert config["user_id"] == "owner"
    assert config["channel_type"] == "webhook"


def test_new_bot_credentials_are_encrypted_fields():
    assert {
        "client_secret",
        "bot_secret",
        "webhook_secret",
        "bot_token",
        "app_token",
    } <= SENSITIVE_FIELDS
