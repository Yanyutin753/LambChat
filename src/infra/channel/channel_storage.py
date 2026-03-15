"""Generic channel configuration storage using MongoDB.

Stores user-level channel configurations with encrypted sensitive fields.
Supports multiple channel types (Feishu, WeChat, DingTalk, etc.)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings
from src.kernel.schemas.channel import (
    ChannelConfigResponse,
    ChannelConfigStatus,
    ChannelType,
)

logger = logging.getLogger(__name__)

# Fields that should be encrypted
SENSITIVE_FIELDS = frozenset(
    {"app_secret", "secret", "token", "password", "api_key", "access_token"}
)


class ChannelStorage:
    """
    Generic channel configuration storage.

    Stores per-user channel configurations in MongoDB.
    Each user can have one configuration per channel type.
    """

    def __init__(self):
        self._client = None
        self._collection = None

    def _get_collection(self):
        """Get channel config collection lazily"""
        if self._collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._collection = db["user_channel_configs"]
        return self._collection

    async def get_config(self, user_id: str, channel_type: ChannelType) -> Optional[dict[str, Any]]:
        """Get channel configuration for a user"""
        collection = self._get_collection()
        doc = await collection.find_one({"user_id": user_id, "channel_type": channel_type.value})
        if doc:
            return self._doc_to_config(doc)
        return None

    async def create_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        config: dict[str, Any],
        enabled: bool = True,
    ) -> dict[str, Any]:
        """Create channel configuration for a user"""
        collection = self._get_collection()

        # Check if config already exists
        existing = await collection.find_one(
            {"user_id": user_id, "channel_type": channel_type.value}
        )
        if existing:
            raise ValueError(f"{channel_type.value} configuration already exists for this user")

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "user_id": user_id,
            "channel_type": channel_type.value,
            "config": self._encrypt_config(config),
            "enabled": enabled,
            "created_at": now,
            "updated_at": now,
        }

        await collection.insert_one(doc)
        logger.info(f"Created {channel_type.value} config for user {user_id}")

        return self._doc_to_config(doc)

    async def update_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        config: dict[str, Any],
        enabled: Optional[bool] = None,
    ) -> Optional[dict[str, Any]]:
        """Update channel configuration for a user"""
        collection = self._get_collection()

        doc = await collection.find_one({"user_id": user_id, "channel_type": channel_type.value})
        if not doc:
            return None

        update_data: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "config": self._encrypt_config(config),
        }

        if enabled is not None:
            update_data["enabled"] = enabled

        await collection.update_one(
            {"user_id": user_id, "channel_type": channel_type.value},
            {"$set": update_data},
        )
        logger.info(f"Updated {channel_type.value} config for user {user_id}")

        updated_doc = await collection.find_one(
            {"user_id": user_id, "channel_type": channel_type.value}
        )
        return self._doc_to_config(updated_doc) if updated_doc else None

    async def delete_config(self, user_id: str, channel_type: ChannelType) -> bool:
        """Delete channel configuration for a user"""
        collection = self._get_collection()
        result = await collection.delete_one(
            {"user_id": user_id, "channel_type": channel_type.value}
        )

        if result.deleted_count > 0:
            logger.info(f"Deleted {channel_type.value} config for user {user_id}")
            return True
        return False

    async def get_response(
        self,
        user_id: str,
        channel_type: ChannelType,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[ChannelConfigResponse]:
        """Get channel configuration response (with masked sensitive fields)"""
        config = await self.get_config(user_id, channel_type)
        if not config:
            return None

        # Get sensitive field names from metadata
        sensitive_fields = set(SENSITIVE_FIELDS)
        if metadata:
            for field in metadata.get("config_fields", []):
                if field.get("sensitive"):
                    sensitive_fields.add(field["name"])

        masked_config = self._mask_config(config, sensitive_fields)

        return ChannelConfigResponse(
            channel_type=channel_type,
            user_id=user_id,
            enabled=config.get("enabled", True),
            config=masked_config,
            capabilities=metadata.get("capabilities", []) if metadata else [],
            created_at=config.get("created_at"),
            updated_at=config.get("updated_at"),
        )

    async def get_status(self, user_id: str, channel_type: ChannelType) -> ChannelConfigStatus:
        """Get channel connection status for a user"""
        config = await self.get_config(user_id, channel_type)
        if not config:
            return ChannelConfigStatus(channel_type=channel_type, enabled=False, connected=False)

        return ChannelConfigStatus(
            channel_type=channel_type,
            enabled=config.get("enabled", True),
            connected=False,  # Will be updated by channel manager
        )

    async def list_user_configs(self, user_id: str) -> list[dict[str, Any]]:
        """List all channel configurations for a user"""
        collection = self._get_collection()
        configs = []
        async for doc in collection.find({"user_id": user_id}):
            configs.append(self._doc_to_config(doc))
        return configs

    async def list_enabled_configs(self, channel_type: ChannelType) -> list[dict[str, Any]]:
        """List all enabled configurations for a channel type (for channel manager)"""
        collection = self._get_collection()
        configs = []
        async for doc in collection.find({"channel_type": channel_type.value, "enabled": True}):
            configs.append(self._doc_to_config(doc))
        return configs

    def _encrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Encrypt sensitive fields in config"""
        encrypted = {}
        for key, value in config.items():
            if key in SENSITIVE_FIELDS and isinstance(value, str) and value:
                encrypted[key] = encrypt_value({"value": value})
            else:
                encrypted[key] = value
        return encrypted

    def _decrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Decrypt sensitive fields in config"""
        from src.infra.mcp.encryption import DecryptionError

        decrypted = {}
        for key, value in config.items():
            if key in SENSITIVE_FIELDS and value:
                if isinstance(value, dict):
                    # Encrypted value
                    try:
                        dec = decrypt_value(value)
                        if isinstance(dec, dict):
                            decrypted[key] = dec.get("value", "")
                        else:
                            decrypted[key] = dec
                    except DecryptionError as e:
                        logger.warning(
                            f"Failed to decrypt field '{key}': {e}. "
                            "Config may have been encrypted with a different key. "
                            "Please re-save the channel configuration."
                        )
                        decrypted[key] = None  # Mark as needing re-entry
                else:
                    decrypted[key] = value
            else:
                decrypted[key] = value
        return decrypted

    def _mask_config(self, config: dict[str, Any], sensitive_fields: set[str]) -> dict[str, Any]:
        """Mask sensitive fields in config for display"""
        masked = {}
        for key, value in config.items():
            if key in sensitive_fields:
                if value:
                    masked[key] = "***"
                else:
                    masked[key] = ""
            else:
                masked[key] = value
        return masked

    def _doc_to_config(self, doc: dict) -> dict[str, Any]:
        """Convert MongoDB document to config dict"""
        config = doc.get("config", {})
        decrypted_config = self._decrypt_config(config)

        return {
            "user_id": doc.get("user_id"),  # Include user_id from document
            **decrypted_config,
            "enabled": doc.get("enabled", True),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }

    async def close(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            self._client = None
            self._collection = None
