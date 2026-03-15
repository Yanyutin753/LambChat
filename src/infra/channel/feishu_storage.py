"""
Feishu/Lark configuration storage using MongoDB

Stores user-level Feishu bot configurations with encrypted sensitive fields.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.infra.mcp.encryption import decrypt_value, encrypt_value
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings
from src.kernel.schemas.feishu import (
    FeishuConfig,
    FeishuConfigCreate,
    FeishuConfigResponse,
    FeishuConfigStatus,
    FeishuConfigUpdate,
    FeishuGroupPolicy,
)

logger = logging.getLogger(__name__)


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
            return self._doc_to_config(doc)
        return None

    async def create_config(self, config: FeishuConfigCreate, user_id: str) -> FeishuConfig:
        """Create Feishu configuration for a user"""
        collection = self._get_collection()

        # Check if config already exists
        existing = await collection.find_one({"user_id": user_id})
        if existing:
            raise ValueError("Feishu configuration already exists for this user")

        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "user_id": user_id,
            "app_id": config.app_id,
            "app_secret": self._encrypt_secret(config.app_secret),
            "encrypt_key": config.encrypt_key,
            "verification_token": config.verification_token,
            "react_emoji": config.react_emoji,
            "group_policy": config.group_policy.value,
            "enabled": config.enabled,
            "created_at": now,
            "updated_at": now,
        }

        await collection.insert_one(doc)
        logger.info(f"Created Feishu config for user {user_id}")

        return self._doc_to_config(doc)

    async def update_config(
        self, user_id: str, updates: FeishuConfigUpdate
    ) -> Optional[FeishuConfig]:
        """Update Feishu configuration for a user"""
        collection = self._get_collection()

        doc = await collection.find_one({"user_id": user_id})
        if not doc:
            return None

        update_data: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}

        if updates.app_id is not None:
            update_data["app_id"] = updates.app_id
        if updates.app_secret is not None:
            update_data["app_secret"] = self._encrypt_secret(updates.app_secret)
        if updates.encrypt_key is not None:
            update_data["encrypt_key"] = updates.encrypt_key
        if updates.verification_token is not None:
            update_data["verification_token"] = updates.verification_token
        if updates.react_emoji is not None:
            update_data["react_emoji"] = updates.react_emoji
        if updates.group_policy is not None:
            update_data["group_policy"] = updates.group_policy.value
        if updates.enabled is not None:
            update_data["enabled"] = updates.enabled

        await collection.update_one({"user_id": user_id}, {"$set": update_data})
        logger.info(f"Updated Feishu config for user {user_id}")

        updated_doc = await collection.find_one({"user_id": user_id})
        return self._doc_to_config(updated_doc) if updated_doc else None

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
            enabled=config.enabled,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )

    async def get_status(self, user_id: str) -> FeishuConfigStatus:
        """Get Feishu connection status for a user"""
        config = await self.get_config(user_id)
        if not config:
            return FeishuConfigStatus(enabled=False, connected=False)

        # TODO: Check actual connection status from channel manager
        return FeishuConfigStatus(
            enabled=config.enabled,
            connected=False,  # Will be updated by channel manager
        )

    async def list_enabled_configs(self) -> list[FeishuConfig]:
        """List all enabled Feishu configurations (for channel manager)"""
        collection = self._get_collection()
        configs = []
        async for doc in collection.find({"enabled": True}):
            configs.append(self._doc_to_config(doc))
        return configs

    def _encrypt_secret(self, secret: str) -> dict[str, Any] | str:
        """Encrypt a secret string"""
        if not secret:
            return ""
        # Use the same encryption as MCP
        return encrypt_value({"value": secret})

    def _decrypt_secret(self, encrypted: dict | str) -> str:
        """Decrypt a secret string"""
        if not encrypted:
            return ""
        if isinstance(encrypted, str):
            return encrypted  # Legacy unencrypted
        decrypted = decrypt_value(encrypted)
        if isinstance(decrypted, dict):
            return decrypted.get("value", "")
        return ""

    def _doc_to_config(self, doc: dict) -> FeishuConfig:
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
            app_secret=self._decrypt_secret(doc.get("app_secret", "")),
            encrypt_key=doc.get("encrypt_key", ""),
            verification_token=doc.get("verification_token", ""),
            react_emoji=doc.get("react_emoji", "THUMBSUP"),
            group_policy=FeishuGroupPolicy(doc.get("group_policy", "mention")),
            enabled=doc.get("enabled", True),
            created_at=created_at,
            updated_at=updated_at,
        )

    async def close(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            self._client = None
            self._collection = None
