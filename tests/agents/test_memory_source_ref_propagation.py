"""三个主 agent 的记忆提取触发点结构契约（Codex 式 Phase 1 移植后）。

- run 结束后 kick 的是「空闲会话提取」（schedule_memory_extraction），不再是
  旧的每轮最后一条交换评估器（schedule_auto_memory_capture 已删除）；
- source_refs 的会话/轮次绑定由提取器从 traces 转录生成（extraction.py），
  nodes 不再手工拼装。
"""

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
def test_agent_kicks_memory_extraction_after_run(node_path: str) -> None:
    source = Path(node_path).read_text()

    assert "schedule_memory_extraction(context.user_id)" in source, node_path
    # 旧每轮评估器必须彻底移除
    assert "schedule_auto_memory_capture" not in source, node_path
    assert "resolve_auto_memory_capture_text" not in source, node_path


@pytest.mark.parametrize(
    "node_path",
    [
        "src/agents/fast_agent/nodes.py",
        "src/agents/search_agent/nodes.py",
        "src/agents/team_agent/nodes.py",
    ],
)
def test_agent_memory_kick_is_memory_flag_gated(node_path: str) -> None:
    source = Path(node_path).read_text()

    block = re.search(
        r"if settings\.ENABLE_MEMORY and context\.user_id:[\s\S]*?schedule_memory_extraction\(",
        source,
    )
    assert block is not None, node_path
