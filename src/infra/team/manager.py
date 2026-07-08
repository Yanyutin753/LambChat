"""Team manager."""

import logging
from typing import Optional

from src.infra.persona_preset.manager import PersonaPresetManager
from src.infra.team.storage import TeamStorage
from src.kernel.exceptions import NotFoundError
from src.kernel.schemas.team import (
    TeamCreate,
    TeamListResponse,
    TeamMemberResponse,
    TeamPreferenceUpdate,
    TeamResponse,
    TeamUpdate,
)
from src.kernel.schemas.user import TokenPayload

logger = logging.getLogger(__name__)


class TeamManager:
    """Business logic for teams."""

    def __init__(
        self,
        storage: TeamStorage | None = None,
        persona_manager: PersonaPresetManager | None = None,
    ) -> None:
        self.storage = storage or TeamStorage()
        self.persona_manager = persona_manager or PersonaPresetManager()

    # ── Internal helpers ──

    async def _hydrate_member_display_metadata(self, team: TeamResponse) -> TeamResponse:
        """Fill role_name, role_avatar, role_tags from persona presets."""
        hydrated_members = []
        for member in team.members:
            try:
                preset = await self.persona_manager.storage.get_by_id(member.persona_preset_id)
                if preset:
                    member = TeamMemberResponse(
                        member_id=member.member_id,
                        persona_preset_id=member.persona_preset_id,
                        model_id=member.model_id,
                        role_name=preset.get("name", member.role_name),
                        role_avatar=preset.get("avatar", member.role_avatar),
                        role_tags=preset.get("tags", member.role_tags),
                        role_instructions=member.role_instructions,
                        position=member.position,
                        enabled=member.enabled,
                    )
            except Exception:
                logger.warning(
                    "Failed to hydrate member %s (preset %s)",
                    member.member_id,
                    member.persona_preset_id,
                )
            hydrated_members.append(member)
        return team.model_copy(update={"members": hydrated_members})

    async def _validate_member_model_access(
        self,
        members: list,
        *,
        user: TokenPayload | None = None,
    ) -> None:
        """Validate optional per-member model overrides before persistence."""
        model_ids: list[str] = []
        seen: set[str] = set()
        for member in members:
            model_id = getattr(member, "model_id", None)
            if not model_id or model_id in seen:
                continue
            seen.add(model_id)
            model_ids.append(model_id)

        if not model_ids:
            return

        from src.infra.agent.model_storage import get_model_storage

        storage = get_model_storage()
        models = {}
        for model_id in model_ids:
            model = await storage.get(model_id)
            if not model or not model.enabled:
                raise ValueError("team_member_model_unavailable")
            models[model_id] = model

        if user is None:
            return

        from src.infra.agent.model_access import resolve_user_allowed_model_ids

        allowed_model_ids = await resolve_user_allowed_model_ids(user)
        if allowed_model_ids is None:
            return

        allowed = set(allowed_model_ids)
        for model_id, model in models.items():
            if model_id not in allowed and model.value not in allowed:
                raise ValueError("team_member_model_not_allowed")

    # ── CRUD ──

    async def create_team(
        self,
        team_data: TeamCreate,
        *,
        owner_user_id: str,
        user: TokenPayload | None = None,
    ) -> TeamResponse:
        """Create a new team."""
        await self._validate_member_model_access(team_data.members, user=user)
        members_data = [m.model_dump(mode="json") for m in team_data.members]
        team = await self.storage.create_team(
            owner_user_id=owner_user_id,
            name=team_data.name,
            description=team_data.description,
            avatar=team_data.avatar,
            tags=team_data.tags,
            members=members_data,
            default_member_id=team_data.default_member_id,
            team_instructions=team_data.team_instructions,
            run_in_sandbox=team_data.run_in_sandbox,
            starter_prompts=[
                prompt.model_dump(mode="json") for prompt in team_data.starter_prompts
            ],
        )
        return await self._hydrate_member_display_metadata(team)

    async def get_team(
        self,
        team_id: str,
        *,
        owner_user_id: str,
    ) -> TeamResponse:
        """Get a team by ID."""
        team = await self.storage.get_team(team_id, owner_user_id=owner_user_id)
        if not team:
            raise NotFoundError("team_not_found")
        return await self._hydrate_member_display_metadata(team)

    async def list_teams(
        self,
        *,
        owner_user_id: str,
        skip: int = 0,
        limit: int = 100,
        favorite: bool | None = None,
        pinned: bool | None = None,
        q: str | None = None,
        tag: str | None = None,
    ) -> TeamListResponse:
        """List teams for an owner."""
        teams, total = await self.storage.list_teams(
            owner_user_id=owner_user_id,
            skip=skip,
            limit=limit,
            favorite=favorite,
            pinned=pinned,
            q=q,
            tag=tag,
        )
        hydrated = []
        for team in teams:
            hydrated.append(await self._hydrate_member_display_metadata(team))
        return TeamListResponse(teams=hydrated, total=total, skip=skip, limit=limit)

    async def update_preference(
        self,
        team_id: str,
        preference: TeamPreferenceUpdate,
        *,
        owner_user_id: str,
    ) -> TeamResponse:
        """Update the current user's favorite/pinned state for a team."""
        team = await self.get_team(team_id, owner_user_id=owner_user_id)
        update = preference.model_dump(mode="json")
        pref = await self.storage.update_user_preference(
            user_id=owner_user_id,
            team_id=team_id,
            update=update,
        )
        return team.model_copy(update=pref)

    async def update_team(
        self,
        team_id: str,
        team_data: TeamUpdate,
        *,
        owner_user_id: str,
        user: TokenPayload | None = None,
    ) -> TeamResponse:
        """Update a team."""
        if team_data.members is not None:
            await self._validate_member_model_access(team_data.members, user=user)
        update = team_data.model_dump(mode="json", exclude_unset=True)
        # Convert member models to dicts for storage
        if "members" in update and update["members"] is not None:
            update["members"] = [m if isinstance(m, dict) else m for m in update["members"]]
        team = await self.storage.update_team(
            team_id,
            owner_user_id=owner_user_id,
            update=update,
        )
        if not team:
            raise NotFoundError("team_not_found")
        return await self._hydrate_member_display_metadata(team)

    async def delete_team(
        self,
        team_id: str,
        *,
        owner_user_id: str,
    ) -> bool:
        """Delete a team."""
        deleted = await self.storage.delete_team(team_id, owner_user_id=owner_user_id)
        if not deleted:
            raise NotFoundError("team_not_found")
        return True

    async def clone_team(
        self,
        team_id: str,
        *,
        owner_user_id: str,
        new_name: str | None = None,
    ) -> TeamResponse:
        """Clone a team."""
        cloned = await self.storage.clone_team(
            team_id,
            owner_user_id=owner_user_id,
            new_name=new_name,
        )
        if not cloned:
            raise NotFoundError("team_not_found")
        return await self._hydrate_member_display_metadata(cloned)

    # ── Validation & resolution ──

    async def validate_team_members(
        self,
        team: TeamResponse,
    ) -> list[TeamMemberResponse]:
        """Return active members with validation. Logs warnings for missing presets."""
        validated = []
        for member in team.active_members:
            try:
                preset = await self.persona_manager.storage.get_by_id(member.persona_preset_id)
                if preset is None:
                    logger.warning(
                        "Member %s references missing preset %s",
                        member.member_id,
                        member.persona_preset_id,
                    )
                    continue
            except Exception:
                logger.warning(
                    "Failed to validate member %s (preset %s)",
                    member.member_id,
                    member.persona_preset_id,
                )
                continue
            validated.append(member)
        return validated

    async def resolve_team_for_runtime(
        self,
        team_id: str,
        *,
        owner_user_id: str,
    ) -> Optional[TeamResponse]:
        """Return team only if it exists and has active members."""
        try:
            team = await self.get_team(team_id, owner_user_id=owner_user_id)
        except NotFoundError:
            return None
        if not team.active_members:
            return None
        validated_members = await self.validate_team_members(team)
        if not validated_members:
            return None
        return team.model_copy(update={"members": validated_members})


_team_manager: Optional[TeamManager] = None


def get_team_manager() -> TeamManager:
    """Get singleton team manager."""
    global _team_manager
    if _team_manager is None:
        _team_manager = TeamManager()
    return _team_manager
