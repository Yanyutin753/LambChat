from __future__ import annotations

from src.agents.fast_agent.graph import FastAgent
from src.agents.search_agent.graph import SearchAgent
from src.agents.team_agent.graph import TeamAgent


def test_agents_expose_code_interpreter_option() -> None:
    for agent_cls in (FastAgent, SearchAgent, TeamAgent):
        option = agent_cls._options["enable_code_interpreter"]

        assert option["type"] == "boolean"
        assert option["default"] is False
