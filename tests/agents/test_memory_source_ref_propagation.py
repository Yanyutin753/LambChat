from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "node_path",
    [
        "src/agents/fast_agent/nodes.py",
        "src/agents/search_agent/nodes.py",
        "src/agents/team_agent/nodes.py",
    ],
)
def test_agent_auto_memory_capture_binds_current_session_and_run(node_path: str) -> None:
    source = Path(node_path).read_text()

    assert "TraceContext.get_request_context()" in source
    assert "ConversationSourceRef(" in source
    assert "source_refs=source_refs" in source
