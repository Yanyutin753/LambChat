import re
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


@pytest.mark.parametrize(
    "node_path",
    [
        "src/agents/fast_agent/nodes.py",
        "src/agents/search_agent/nodes.py",
        "src/agents/team_agent/nodes.py",
    ],
)
def test_agent_auto_memory_capture_waits_for_final_run_completion(node_path: str) -> None:
    source = Path(node_path).read_text()

    memory_block = re.search(
        r"if settings\.ENABLE_MEMORY[\s\S]*?schedule_auto_memory_capture\([^)]*\)",
        source,
    )
    assert memory_block is not None, node_path
    block = memory_block.group(0)
    # ask_human 挂起的 run（waiting_human）不能在挂起瞬间发起记忆评估，
    # 只能在 run 最终 finished 的那一轮捕获
    assert "hitl_suspended" in block, node_path
    assert "hitl_resume is None" not in block, node_path
