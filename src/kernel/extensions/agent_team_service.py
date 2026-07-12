"""Core contract for optional Agent Team directory capabilities."""

from typing import Any, Protocol


class AgentTeamDirectory(Protocol):
    """Read-only team operations used by core surfaces."""

    async def get_team(self, team_id: str, *, owner_user_id: str) -> Any | None: ...

    async def get_team_name(self, team_id: str) -> str: ...

    async def search_teams(
        self,
        *,
        owner_user_id: str,
        query: str,
        limit: int,
    ) -> list[Any]: ...


_directory: AgentTeamDirectory | None = None


def register_agent_team_directory(directory: AgentTeamDirectory | None) -> None:
    """Register or clear the Agent Team-owned directory implementation."""
    global _directory
    _directory = directory


def get_agent_team_directory() -> AgentTeamDirectory | None:
    """Return the registered directory without importing plugin code."""
    return _directory
