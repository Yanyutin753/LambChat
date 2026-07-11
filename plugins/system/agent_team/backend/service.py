"""Agent Team implementation of the core directory contract."""

from typing import Any

from bson import ObjectId

from plugins.system.agent_team.backend.domain.manager import TeamManager
from plugins.system.agent_team.backend.domain.storage import TeamStorage
from src.kernel.extensions.agent_team_service import register_agent_team_directory


class AgentTeamDirectoryService:
    """Expose read-only team lookup without leaking plugin imports into core."""

    async def get_team(self, team_id: str, *, owner_user_id: str) -> Any | None:
        return await TeamStorage().get_team(team_id, owner_user_id=owner_user_id)

    async def get_team_name(self, team_id: str) -> str:
        try:
            query_id: ObjectId | str = ObjectId(team_id)
        except Exception:
            query_id = team_id
        doc = await TeamStorage().collection.find_one(
            {"_id": query_id},
            {"_id": 0, "name": 1},
        )
        name = (doc or {}).get("name")
        return name if isinstance(name, str) else ""

    async def search_teams(
        self,
        *,
        owner_user_id: str,
        query: str,
        limit: int,
    ) -> list[Any]:
        response = await TeamManager().list_teams(
            owner_user_id=owner_user_id,
            q=query,
            limit=limit,
        )
        return list(response.teams)


register_agent_team_directory(AgentTeamDirectoryService())
