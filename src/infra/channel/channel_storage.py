"""Generic channel configuration storage using MongoDB.

Stores user-level channel configurations with encrypted sensitive fields.
Supports multiple channel types (Feishu, WeChat, DingTalk, etc.)
"""

import asyncio
import types
import uuid
from typing import Any, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now_iso
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
CHANNEL_CONFIG_LIST_LIMIT = 200


class ChannelStorage:
    """
    Generic channel configuration storage.

    Stores per-user channel configurations in MongoDB.
    Each user can have multiple configurations per channel type (multi-instance support).
    """

    _indexes_done = False
    _indexes_task: asyncio.Task | None = None
    _indexes_lock: asyncio.Lock | None = None

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

    async def ensure_indexes_if_needed(self) -> None:
        """Ensure channel indexes exist once per process."""
        cls = type(self)
        if cls._indexes_done:
            return

        if cls._indexes_lock is None:
            cls._indexes_lock = asyncio.Lock()

        async with cls._indexes_lock:
            if cls._indexes_done:
                return
            if cls._indexes_task is None or cls._indexes_task.cancelled():
                cls._indexes_task = asyncio.create_task(self._ensure_indexes())
            task = cls._indexes_task

        succeeded = await task
        if succeeded:
            cls._indexes_done = True
            return

        async with cls._indexes_lock:
            if cls._indexes_task is task:
                cls._indexes_task = None

    async def _ensure_indexes(self) -> bool:
        try:
            collection = self._get_collection()
            await collection.create_index(
                [("user_id", 1), ("channel_type", 1), ("instance_id", 1)],
                name="user_channel_instance_idx",
                unique=True,
                background=True,
            )
            await collection.create_index(
                [("channel_type", 1), ("enabled", 1)],
                name="channel_enabled_idx",
                background=True,
            )
            return True
        except Exception as e:
            logger.warning(f"Failed to create channel indexes: {e}")
            return False

    async def get_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        instance_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Get channel configuration for a user and optionally instance"""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()

        query: dict[str, Any] = {"user_id": user_id, "channel_type": channel_type.value}
        if instance_id:
            query["instance_id"] = instance_id

        doc = await collection.find_one(query)
        if doc:
            return await self._doc_to_config(doc)
        return None

    async def create_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        config: dict[str, Any],
        name: str,
        enabled: bool = True,
        agent_id: str | None = None,
        model_id: str | None = None,
        project_id: str | None = None,
        plugin_options: dict[str, dict[str, Any]] | None = None,
        persona_preset_id: str | None = None,
    ) -> dict[str, Any]:
        """Create channel configuration for a user"""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()

        # Generate unique instance_id
        instance_id = str(uuid.uuid4())

        now = utc_now_iso()
        doc = {
            "user_id": user_id,
            "channel_type": channel_type.value,
            "instance_id": instance_id,
            "name": name,
            "config": await self._encrypt_config(config),
            "enabled": enabled,
            "agent_id": agent_id,
            "model_id": model_id,
            "project_id": project_id,
            "plugin_options": plugin_options or {},
            "persona_preset_id": persona_preset_id,
            "created_at": now,
            "updated_at": now,
        }

        await collection.insert_one(doc)
        logger.info(
            f"Created {channel_type.value} config '{name}' ({instance_id}) for user {user_id}"
        )

        return await self._doc_to_config(doc)

    async def update_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        config: dict[str, Any],
        instance_id: str,
        enabled: Optional[bool] = None,
        name: Optional[str] = None,
        agent_id: Optional[str] | types.EllipsisType = ...,
        model_id: Optional[str] | types.EllipsisType = ...,
        project_id: Optional[str] | types.EllipsisType = ...,
        plugin_options: Optional[dict[str, dict[str, Any]]] | types.EllipsisType = ...,
        persona_preset_id: Optional[str] | types.EllipsisType = ...,
    ) -> Optional[dict[str, Any]]:
        """Update channel configuration for a user"""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()

        doc = await collection.find_one(
            {"user_id": user_id, "channel_type": channel_type.value, "instance_id": instance_id}
        )
        if not doc:
            return None

        update_data: dict[str, Any] = {
            "updated_at": utc_now_iso(),
            "config": await self._encrypt_config(config),
        }

        if enabled is not None:
            update_data["enabled"] = enabled
        if name is not None:
            update_data["name"] = name
        if agent_id is not ...:
            update_data["agent_id"] = agent_id
        if model_id is not ...:
            update_data["model_id"] = model_id
        if project_id is not ...:
            update_data["project_id"] = project_id
        if plugin_options is not ...:
            update_data["plugin_options"] = plugin_options or {}
        if persona_preset_id is not ...:
            update_data["persona_preset_id"] = persona_preset_id

        await collection.update_one(
            {"user_id": user_id, "channel_type": channel_type.value, "instance_id": instance_id},
            {"$set": update_data},
        )
        logger.info(f"Updated {channel_type.value} config ({instance_id}) for user {user_id}")

        updated_doc = await collection.find_one(
            {"user_id": user_id, "channel_type": channel_type.value, "instance_id": instance_id}
        )
        return await self._doc_to_config(updated_doc) if updated_doc else None

    async def delete_config(
        self,
        user_id: str,
        channel_type: ChannelType,
        instance_id: Optional[str] = None,
    ) -> bool:
        """Delete channel configuration for a user"""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()

        query: dict[str, Any] = {"user_id": user_id, "channel_type": channel_type.value}
        if instance_id:
            query["instance_id"] = instance_id

        result = await collection.delete_one(query)

        if result.deleted_count > 0:
            logger.info(f"Deleted {channel_type.value} config ({instance_id}) for user {user_id}")
            return True
        return False

    async def clear_project_id(self, project_id: str, user_id: str) -> int:
        """Clear a project reference from channel configurations for a user."""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()
        result = await collection.update_many(
            {"user_id": user_id, "project_id": project_id},
            {
                "$set": {
                    "project_id": None,
                    "updated_at": utc_now_iso(),
                }
            },
        )
        return result.modified_count

    async def clear_config_project_id(
        self, user_id: str, channel_type: ChannelType, instance_id: str
    ) -> int:
        """Clear the project reference for one channel configuration."""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()
        result = await collection.update_one(
            {"user_id": user_id, "channel_type": channel_type.value, "instance_id": instance_id},
            {
                "$set": {
                    "project_id": None,
                    "updated_at": utc_now_iso(),
                }
            },
        )
        return result.modified_count

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

        return self.build_response_from_config(config, channel_type, user_id, metadata)

    def build_response_from_config(
        self,
        config: dict[str, Any],
        channel_type: ChannelType,
        user_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ChannelConfigResponse:
        """Build a response from an already loaded config."""

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
            model_id=config.get("model_id"),
            project_id=config.get("project_id"),
            team_id=config.get("team_id"),
            plugin_options=config.get("plugin_options") or {},
            persona_preset_id=config.get("persona_preset_id"),
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

        return self.build_status_from_config(config, channel_type)

    def build_status_from_config(
        self,
        config: dict[str, Any],
        channel_type: ChannelType,
    ) -> ChannelConfigStatus:
        """Build a status object from an already loaded config."""

        return ChannelConfigStatus(
            channel_type=channel_type,
            enabled=config.get("enabled", True),
            connected=False,  # Will be updated by channel manager
        )

    async def list_user_configs(self, user_id: str) -> list[dict[str, Any]]:
        """List all channel configurations for a user"""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()
        configs = []
        async for doc in collection.find({"user_id": user_id}).limit(CHANNEL_CONFIG_LIST_LIMIT):
            configs.append(await self._doc_to_config(doc))
        return configs

    async def list_user_configs_by_type(
        self, user_id: str, channel_type: ChannelType
    ) -> list[dict[str, Any]]:
        """List channel configurations for a user and channel type."""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()
        configs = []
        async for doc in collection.find(
            {"user_id": user_id, "channel_type": channel_type.value}
        ).limit(CHANNEL_CONFIG_LIST_LIMIT):
            configs.append(await self._doc_to_config(doc))
        return configs

    async def count_user_configs(self, user_id: str) -> int:
        """Count channel configurations for a user without loading config payloads."""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()
        return int(await collection.count_documents({"user_id": user_id}))

    async def count_user_configs_by_type(self, user_id: str, channel_type: ChannelType) -> int:
        """Count channel configurations for a user and type without loading payloads."""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()
        return int(
            await collection.count_documents(
                {"user_id": user_id, "channel_type": channel_type.value}
            )
        )

    async def list_enabled_configs(self, channel_type: ChannelType) -> list[dict[str, Any]]:
        """List all enabled configurations for a channel type (for channel manager)"""
        configs = []
        async for config in self.iter_enabled_configs(channel_type):
            configs.append(config)
        return configs

    async def iter_enabled_configs(self, channel_type: ChannelType):
        """Iterate enabled configurations for a channel type without materializing all rows."""
        await self.ensure_indexes_if_needed()
        collection = self._get_collection()
        cursor = collection.find({"channel_type": channel_type.value, "enabled": True}).limit(
            CHANNEL_CONFIG_LIST_LIMIT
        )
        async for doc in cursor:
            yield await self._doc_to_config(doc)

    async def _encrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Encrypt sensitive fields in config"""
        encrypted = {}
        for key, value in config.items():
            if key in SENSITIVE_FIELDS and isinstance(value, str) and value:
                encrypted[key] = await run_blocking_io(encrypt_value, {"value": value})
            else:
                encrypted[key] = value
        return encrypted

    async def _decrypt_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Decrypt sensitive fields in config"""
        from src.infra.mcp.encryption import DecryptionError

        decrypted = {}
        for key, value in config.items():
            if key in SENSITIVE_FIELDS and value:
                if isinstance(value, dict):
                    # Encrypted value
                    try:
                        dec = await run_blocking_io(decrypt_value, value)
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

    async def _doc_to_config(self, doc: dict) -> dict[str, Any]:
        """Convert MongoDB document to config dict"""
        config = doc.get("config", {})
        decrypted_config = await self._decrypt_config(config)

        return {
            "user_id": doc.get("user_id"),  # Include user_id from document
            "channel_type": doc.get("channel_type"),
            "instance_id": doc.get("instance_id"),
            "name": doc.get("name"),
            **decrypted_config,
            "enabled": doc.get("enabled", True),
            "agent_id": doc.get("agent_id"),
            "model_id": doc.get("model_id"),
            "project_id": doc.get("project_id"),
            "team_id": doc.get("team_id"),
            "plugin_options": doc.get("plugin_options") or {},
            "persona_preset_id": doc.get("persona_preset_id"),
            "created_at": doc.get("created_at"),
            "updated_at": doc.get("updated_at"),
        }

    async def close(self):
        """Close MongoDB connection (only clears local refs, does not close global client)"""
        self._collection = None
