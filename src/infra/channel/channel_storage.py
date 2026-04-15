"""Generic channel configuration storage using MongoDB.

Stores user-level channel configurations with encrypted sensitive fields.
Supports multiple channel types (Feishu, WeChat, DingTalk, etc.)
"""

import types
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from src.infra.logging import get_logger
from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings
from src.kernel.schemas.channel import (
    ChannelConfigResponse,
    ChannelConfigStatus,
    ChannelType,
)

logger = get_logger(__name__)

# Fields that should be encrypted
SENSITIVE_FIELDS = frozenset(
    {"app_secret", "secret", "token", "password", "api_key", "access_token"}
)


class ChannelStorage:
    """
    Generic channel configuration storage.

    Stores per-user channel configurations in MongoDB.
    Each user can have multiple configurations per channel type (multi-instance support).
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

    async def get_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        instance_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Get channel configuration for a user and optionally instance"""
        collection = self._get_collection()

        query: dict[str, Any] = {"user_id": user_id, "channel_type": channel_type.value}
        if instance_id:
            query["instance_id"] = instance_id

        doc = await collection.find_one(query)
        if doc:
            return self._doc_to_config(doc)
        return None

    async def create_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        config: dict[str, Any],
        name: str,
        enabled: bool = True,
        agent_id: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        """Create channel configuration for a user"""
        collection = self._get_collection()

        # Generate unique instance_id
        instance_id = str(uuid.uuid4())

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "user_id": user_id,
            "channel_type": channel_type.value,
            "instance_id": instance_id,
            "name": name,
            "config": self._encrypt_config(config),
            "enabled": enabled,
            "agent_id": agent_id,
            "project_id": project_id,
            "created_at": now,
            "updated_at": now,
        }

        await collection.insert_one(doc)
        logger.info(
            f"Created {channel_type.value} config '{name}' ({instance_id}) for user {user_id}"
        )

        return self._doc_to_config(doc)

    async def update_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        config: dict[str, Any],
        instance_id: str,
        enabled: Optional[bool] = None,
        name: Optional[str] = None,
        agent_id: Optional[str] | types.EllipsisType = ...,
        project_id: Optional[str] | types.EllipsisType = ...,
    ) -> Optional[dict[str, Any]]:
        """Update channel configuration for a user"""
        collection = self._get_collection()

        doc = await collection.find_one(
            {"user_id": user_id, "channel_type": channel_type.value, "instance_id": instance_id}
        )
        if not doc:
            return None

        update_data: dict[str, Any] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "config": self._encrypt_config(config),
        }

        if enabled is not None:
            update_data["enabled"] = enabled
        if name is not None:
            update_data["name"] = name
        if agent_id is not ...:
            update_data["agent_id"] = agent_id
        if project_id is not ...:
            update_data["project_id"] = project_id

        await collection.update_one(
            {"user_id": user_id, "channel_type": channel_type.value, "instance_id": instance_id},
            {"$set": update_data},
        )
        logger.info(f"Updated {channel_type.value} config ({instance_id}) for user {user_id}")

        updated_doc = await collection.find_one(
            {"user_id": user_id, "channel_type": channel_type.value, "instance_id": instance_id}
        )
        return self._doc_to_config(updated_doc) if updated_doc else None

    async def delete_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        instance_id: Optional[str] = None,
    ) -> bool:
        """Delete channel configuration for a user"""
        collection = self._get_collection()

        query: dict[str, Any] = {"user_id": user_id, "channel_type": channel_type.value}
        if instance_id:
            query["instance_id"] = instance_id

        result = await collection.delete_one(query)

        if result.deleted_count > 0:
            logger.info(f"Deleted {channel_type.value} config ({instance_id}) for user {user_id}")
            return True
        return False

    async def get_response(
        self,
        user_id: str,
        channel_type: ChannelType,
        instance_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[ChannelConfigResponse]:
        """Get channel configuration response (with masked sensitive fields)"""
        config = await self.get_config(user_id, channel_type, instance_id)
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
            id=config.get("instance_id", ""),
            channel_type=channel_type,
            name=config.get("name", ""),
            user_id=user_id,
            enabled=config.get("enabled", True),
            config=masked_config,
            capabilities=metadata.get("capabilities", []) if metadata else [],
            agent_id=config.get("agent_id"),
            project_id=config.get("project_id"),
            created_at=config.get("created_at"),
            updated_at=config.get("updated_at"),
        )

    async def get_status(
        self,
        user_id: str,
        channel_type: ChannelType,
        instance_id: Optional[str] = None,
    ) -> ChannelConfigStatus:
        """Get channel connection status for a user"""
        config = await self.get_config(user_id, channel_type, instance_id)
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
            "channel_type": doc.get("channel_type"),
            "instance_id": doc.get("instance_id"),
            "name": doc.get("name"),
            **decrypted_config,
            "enabled": doc.get("enabled", True),
            "agent_id": doc.get("agent_id"),
            "project_id": doc.get("project_id"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }

    async def close(self):
        """Close MongoDB connection (only clears local refs, does not close global client)"""
        self._collection = None
