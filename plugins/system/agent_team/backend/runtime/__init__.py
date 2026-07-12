"""Team Agent module."""

from plugins.system.agent_team.backend.runtime.prompt import build_team_members_description

__all__ = ["build_team_members_description"]


def __getattr__(name):
    """Lazy import for heavy dependencies (graph, nodes)."""
    if name == "TeamAgent":
        from plugins.system.agent_team.backend.runtime.graph import TeamAgent

        return TeamAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
