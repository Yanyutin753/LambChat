from __future__ import annotations

from pathlib import Path

AGENT_NODES_DIR = Path(__file__).resolve().parents[2] / "src" / "agents"


def test_all_deep_agent_nodes_install_main_agent_context_middleware() -> None:
    agent_node_sources = sorted(AGENT_NODES_DIR.glob("*/nodes.py"))
    deep_agent_nodes = [
        path for path in agent_node_sources if "create_deep_agent(" in path.read_text()
    ]

    assert deep_agent_nodes
    for path in deep_agent_nodes:
        source = path.read_text()
        assert "MainAgentContextMiddleware" in source, path
        assert "user_middleware.append(MainAgentContextMiddleware(backend=backend))" in source, path
        assert "SubagentResultHandoffMiddleware" in source, path
        assert (
            "user_middleware.append(SubagentResultHandoffMiddleware(backend=backend))" in source
        ), path
