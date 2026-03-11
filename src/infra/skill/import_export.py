"""
Skill import/export mixin for import and export operations
"""

import logging
from typing import Any

from src.infra.skill.converters import doc_to_export_dict
from src.kernel.schemas.skill import (
    GitHubInstallRequest,
    SkillCreate,
    SkillExportResponse,
    SkillImportRequest,
    SkillImportResponse,
    SkillSource,
    SkillUpdate,
)

logger = logging.getLogger(__name__)


class SkillImportExportMixin:
    """
    Mixin providing import/export functionality for skills.

    This mixin handles:
    - Importing skills from JSON configuration
    - Exporting skills to JSON configuration
    - Installing skills from GitHub repositories
    """

    async def get_system_skill(self, name: str) -> Any:
        """Get a system skill by name (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement get_system_skill")

    async def get_user_skill(self, name: str, user_id: str) -> Any:
        """Get a user's skill by name (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement get_user_skill")

    async def update_system_skill(self, name: str, updates: SkillUpdate, admin_user_id: str) -> Any:
        """Update a system skill (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement update_system_skill")

    async def create_system_skill(self, skill: SkillCreate, admin_user_id: str) -> Any:
        """Create a system skill (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement create_system_skill")

    async def update_user_skill(self, name: str, updates: SkillUpdate, user_id: str) -> Any:
        """Update a user skill (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement update_user_skill")

    async def create_user_skill(self, skill: SkillCreate, user_id: str) -> Any:
        """Create a user skill (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement create_user_skill")

    def _get_system_collection(self) -> Any:
        """Get system skills collection lazily (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement _get_system_collection")

    def _get_user_collection(self) -> Any:
        """Get user skills collection lazily (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement _get_user_collection")

    async def import_skills(
        self,
        import_data: SkillImportRequest,
        user_id: str,
        is_admin: bool = False,
    ) -> SkillImportResponse:
        """
        Import skills from JSON configuration.

        Returns SkillImportResponse with counts and errors.
        """
        imported = 0
        skipped = 0
        errors = []

        for name, config in import_data.skills.items():
            try:
                # Parse source
                source_str = config.get("source", "manual")
                try:
                    source = SkillSource(source_str)
                except ValueError:
                    source = SkillSource.MANUAL

                # Create skill object
                skill = SkillCreate(
                    name=name,
                    description=config.get("description", ""),
                    content=config.get("content", ""),
                    enabled=config.get("enabled", True),
                    source=source,
                    github_url=config.get("github_url"),
                    version=config.get("version"),
                )

                # Check if exists
                existing: Any = None
                if is_admin:
                    existing = await self.get_system_skill(name)
                else:
                    existing = await self.get_user_skill(name, user_id)

                if existing and not import_data.overwrite:
                    skipped += 1
                    continue

                # Create or update
                if is_admin:
                    if existing:
                        await self.update_system_skill(
                            name,
                            SkillUpdate(
                                description=skill.description,
                                content=skill.content,
                                enabled=skill.enabled,
                                version=skill.version,
                                is_system=True,
                            ),
                            user_id,
                        )
                    else:
                        await self.create_system_skill(skill, user_id)
                else:
                    if existing:
                        await self.update_user_skill(
                            name,
                            SkillUpdate(
                                description=skill.description,
                                content=skill.content,
                                enabled=skill.enabled,
                                version=skill.version,
                                is_system=False,
                            ),
                            user_id,
                        )
                    else:
                        await self.create_user_skill(skill, user_id)

                imported += 1

            except Exception as e:
                errors.append(f"Error importing '{name}': {str(e)}")

        return SkillImportResponse(
            message=f"Imported {imported} skills, skipped {skipped}",
            imported_count=imported,
            skipped_count=skipped,
            errors=errors,
        )

    async def export_user_skills(self, user_id: str) -> SkillExportResponse:
        """Export user's skills as JSON configuration"""
        user_collection = self._get_user_collection()
        skills = {}

        async for doc in user_collection.find({"user_id": user_id}):
            skills[doc["name"]] = doc_to_export_dict(doc)

        return SkillExportResponse(skills=skills)

    async def export_all_skills(self) -> SkillExportResponse:
        """Export all skills (system only, admin)"""
        system_collection = self._get_system_collection()
        skills = {}

        async for doc in system_collection.find({}):
            skills[doc["name"]] = doc_to_export_dict(doc)

        return SkillExportResponse(skills=skills)

    async def install_github_skills(
        self,
        install_request: GitHubInstallRequest,
        skills_data: list[dict[str, Any]],
        user_id: str,
        is_admin: bool = False,
    ) -> SkillImportResponse:
        """
        Install skills from GitHub repository.

        Args:
            install_request: GitHub install request
            skills_data: List of skill data from GitHub sync service
            user_id: User ID performing the install
            is_admin: Whether the user is an admin

        Returns:
            SkillImportResponse with counts and errors
        """
        imported = 0
        skipped = 0
        errors = []

        # Filter skills if specific names provided
        if install_request.skill_names:
            skills_data = [s for s in skills_data if s.get("name") in install_request.skill_names]

        for skill_data in skills_data:
            try:
                name = skill_data["name"]

                # Get content and files dict
                content = skill_data.get("content", "")
                # Use files from skill_data if available, otherwise create from content
                files = skill_data.get("files")
                if not files:
                    files = {"SKILL.md": content} if content else {}

                # Create skill object
                skill = SkillCreate(
                    name=name,
                    description=skill_data.get("description", ""),
                    content=content,
                    files=files,
                    enabled=True,
                    source=SkillSource.GITHUB,
                    github_url=install_request.repo_url,
                    version=skill_data.get("version"),
                )

                # Check if exists
                existing: Any = None
                if is_admin:
                    existing = await self.get_system_skill(name)
                else:
                    existing = await self.get_user_skill(name, user_id)

                if existing:
                    skipped += 1
                    continue

                # Create skill (this will sync files internally)
                if is_admin:
                    await self.create_system_skill(skill, user_id)
                else:
                    await self.create_user_skill(skill, user_id)

                imported += 1

            except Exception as e:
                errors.append(f"Error installing '{skill_data.get('name', 'unknown')}': {str(e)}")

        return SkillImportResponse(
            message=f"Installed {imported} skills from GitHub, skipped {skipped}",
            imported_count=imported,
            skipped_count=skipped,
            errors=errors,
        )
