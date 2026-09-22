"""
Feishu/Lark configuration storage using MongoDB

Stores user-level Feishu bot configurations with encrypted sensitive fields.
"""

from datetime import datetime
from typing import Any, Optional

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now_iso
from src.kernel.config import settings
from src.kernel.schemas.feishu import (
    DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
    FeishuConfig,
    FeishuConfigCreate,
    FeishuConfigResponse,
    FeishuConfigStatus,
    FeishuConfigUpdate,
    FeishuGroupPolicy,
)

logger = get_logger(__name__)

FEISHU_CONFIG_LIST_LIMIT = 200


class FeishuStorage:
    """
    Feishu configuration storage

    Stores per-user Feishu bot configurations in MongoDB.
    Each user can have their own Feishu bot configuration.
    """

    def __init__(self):
        self._client = None
        self._collection = None

    def _get_collection(self):
        """Get Feishu config collection lazily"""
        if self._collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._collection = db["user_feishu_configs"]
        return self._collection

    async def get_config(self, user_id: str) -> Optional[FeishuConfig]:
        """Get Feishu configuration for a user"""
        collection = self._get_collection()
        doc = await collection.find_one({"user_id": user_id})
        if doc:
            return await self._doc_to_config(doc)
        return None

    async def create_config(self, config: FeishuConfigCreate, user_id: str) -> FeishuConfig:
        """Create Feishu configuration for a user"""
        collection = self._get_collection()

        # Check if config already exists
        existing = await collection.find_one({"user_id": user_id})
        if existing:
            raise ValueError("Feishu configuration already exists for this user")

        now = utc_now_iso()
        doc = {
            "user_id": user_id,
            "app_id": config.app_id,
            "app_secret": await self._encrypt_secret(config.app_secret),
            "encrypt_key": config.encrypt_key,
            "verification_token": config.verification_token,
            "react_emoji": config.react_emoji,
            "group_policy": config.group_policy.value,
            "stream_reply": config.stream_reply,
            "auto_transcribe_audio": config.auto_transcribe_audio,
            "audio_transcribe_prompt": config.audio_transcribe_prompt,
            "enabled": config.enabled,
            "created_at": now,
            "updated_at": now,
        }

        await collection.insert_one(doc)
        logger.info(f"Created Feishu config for user {user_id}")

        return await self._doc_to_config(doc)

    async def update_config(
        self, user_id: str, updates: FeishuConfigUpdate
    ) -> Optional[FeishuConfig]:
        """Update Feishu configuration for a user"""
        collection = self._get_collection()

        doc = await collection.find_one({"user_id": user_id})
        if not doc:
            return None

        update_data: dict[str, Any] = {"updated_at": utc_now_iso()}

        if updates.app_id is not None:
            update_data["app_id"] = updates.app_id
        if updates.app_secret is not None:
            update_data["app_secret"] = await self._encrypt_secret(updates.app_secret)
        if updates.encrypt_key is not None:
            update_data["encrypt_key"] = updates.encrypt_key
        if updates.verification_token is not None:
            update_data["verification_token"] = updates.verification_token
        if updates.react_emoji is not None:
            update_data["react_emoji"] = updates.react_emoji
        if updates.group_policy is not None:
            update_data["group_policy"] = updates.group_policy.value
        if updates.stream_reply is not None:
            update_data["stream_reply"] = updates.stream_reply
        if updates.auto_transcribe_audio is not None:
            update_data["auto_transcribe_audio"] = updates.auto_transcribe_audio
        if updates.audio_transcribe_prompt is not None:
            update_data["audio_transcribe_prompt"] = updates.audio_transcribe_prompt
        if updates.enabled is not None:
            update_data["enabled"] = updates.enabled

        await collection.update_one({"user_id": user_id}, {"$set": update_data})
        logger.info(f"Updated Feishu config for user {user_id}")

        updated_doc = await collection.find_one({"user_id": user_id})
        return await self._doc_to_config(updated_doc) if updated_doc else None

    async def delete_config(self, user_id: str) -> bool:
        """Delete Feishu configuration for a user"""
        collection = self._get_collection()
        result = await collection.delete_one({"user_id": user_id})

        if result.deleted_count > 0:
            logger.info(f"Deleted Feishu config for user {user_id}")
            return True
        return False

    async def get_response(self, user_id: str) -> Optional[FeishuConfigResponse]:
        """Get Feishu configuration response (with masked sensitive fields)"""
        config = await self.get_config(user_id)
        if not config:
            return None

        return FeishuConfigResponse(
            user_id=config.user_id,
            app_id=config.app_id,
            has_app_secret=bool(config.app_secret),
            encrypt_key="***" if config.encrypt_key else "",
            verification_token="***" if config.verification_token else "",
            react_emoji=config.react_emoji,
            group_policy=config.group_policy,
            stream_reply=config.stream_reply,
            auto_transcribe_audio=config.auto_transcribe_audio,
            audio_transcribe_prompt=config.audio_transcribe_prompt,
            enabled=config.enabled,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    async def get_status(self, user_id: str) -> FeishuConfigStatus:
        """Get Feishu connection status for a user"""
        config = await self.get_config(user_id)
        if not config:
            return FeishuConfigStatus(enabled=False, connected=False)

        # Check actual connection status from channel manager
        from src.infra.channel.feishu.manager import get_feishu_channel_manager

        manager = get_feishu_channel_manager()
        is_channel_connected = manager.is_connected(user_id, config.instance_id)

        return FeishuConfigStatus(
            enabled=config.enabled,
            connected=is_channel_connected,
        )

    async def list_enabled_configs(self) -> list[FeishuConfig]:
        """List all enabled Feishu configurations (for channel manager)"""
        collection = self._get_collection()
        configs = []
        async for doc in collection.find({"enabled": True}).limit(FEISHU_CONFIG_LIST_LIMIT):
            configs.append(await self._doc_to_config(doc))
        return configs

    async def _encrypt_secret(self, secret: str) -> dict[str, Any] | str:
        """Encrypt a secret string"""
        if not secret:
            return ""
        # Use the same encryption as MCP
        return await run_long_blocking_io(encrypt_value, {"value": secret})

    async def _decrypt_secret(self, encrypted: dict | str) -> str:
        """Decrypt a secret string"""
        if not encrypted:
            return ""
        if isinstance(encrypted, str):
            return encrypted  # Legacy unencrypted
        decrypted = await run_long_blocking_io(decrypt_value, encrypted)
        if isinstance(decrypted, dict):
            return decrypted.get("value", "")
        return ""

    async def _doc_to_config(self, doc: dict) -> FeishuConfig:
        """Convert MongoDB document to FeishuConfig"""
        created_at = doc.get("created_at")
        updated_at = doc.get("updated_at")

        if created_at and isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if updated_at and isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))

        return FeishuConfig(
            user_id=doc["user_id"],
            app_id=doc["app_id"],
            app_secret=await self._decrypt_secret(doc.get("app_secret", "")),
            encrypt_key=doc.get("encrypt_key", ""),
            verification_token=doc.get("verification_token", ""),
            react_emoji=doc.get("react_emoji", "THUMBSUP"),
            group_policy=FeishuGroupPolicy(doc.get("group_policy", "mention")),
            stream_reply=doc.get("stream_reply", True),
            auto_transcribe_audio=doc.get("auto_transcribe_audio", True),
            audio_transcribe_prompt=doc.get(
                "audio_transcribe_prompt", DEFAULT_AUDIO_TRANSCRIBE_PROMPT
            )
            or DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
            enabled=doc.get("enabled", True),
            created_at=created_at,
            updated_at=updated_at,
        )

    async def close(self):
        """Clear local MongoDB references without closing the global client."""
        self._client = None
        self._collection = None
