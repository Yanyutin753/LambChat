"""Team Agent context — reuses FastAgentContext tool/skill loading."""

from src.agents.fast_agent.context import FastAgentContext


class TeamAgentContext(FastAgentContext):
    """Reuses FastAgentContext tool/skill loading. Team-specific logic is in the node."""

    pass
