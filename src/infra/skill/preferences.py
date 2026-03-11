"""
Skill preferences mixin for user preference management
"""

from datetime import datetime, timezone
from typing import Any


class SkillPreferencesMixin:
    """
    Mixin providing user preference functionality for skills.

    This mixin handles:
    - Getting user preferences for system skills
    - Setting user preferences for system skills
    """

    async def _invalidate_user_skills_cache(self, user_id: str) -> None:
        """Invalidate skills Redis cache for a specific user (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement _invalidate_user_skills_cache")

    def _get_preferences_collection(self) -> Any:
        """Get user skill preferences collection lazily (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement _get_preferences_collection")

    async def _get_user_preferences(self, user_id: str) -> dict[str, bool]:
        """Get user's enabled preferences for system skills"""
        collection = self._get_preferences_collection()
        preferences = {}
        async for doc in collection.find({"user_id": user_id}):
            preferences[doc["skill_name"]] = doc.get("enabled", True)
        return preferences

    async def _set_user_preference(self, skill_name: str, user_id: str, enabled: bool) -> None:
        """Set user's preference for a system skill"""
        collection = self._get_preferences_collection()
        await collection.update_one(
            {"skill_name": skill_name, "user_id": user_id},
            {
                "$set": {
                    "enabled": enabled,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
            upsert=True,
        )

        # Invalidate cache for this user
        await self._invalidate_user_skills_cache(user_id)
