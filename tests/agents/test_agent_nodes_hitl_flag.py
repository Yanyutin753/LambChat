"""结构测试：所有提供 ask_human 工具的 agent 节点都必须在流式执行时
设置 hitl_interrupt_supported，否则 interrupt 模式下 ask_human 会直接抛错。"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

AGENT_NODES = [
    "agents/fast_agent/nodes.py",
    "agents/search_agent/nodes.py",
    "agents/team_agent/nodes.py",
]


def _read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def test_agent_nodes_set_hitl_interrupt_flag() -> None:
    for rel in AGENT_NODES:
        assert "hitl_interrupt_supported.set" in _read(rel), rel


def test_agent_nodes_materialize_ask_human_approvals_after_stream() -> None:
    for rel in AGENT_NODES:
        source = _read(rel)
        assert "materialize_ask_human_approvals" in source, rel
        assert "snapshot.next" in source, rel


def test_agent_nodes_support_hitl_resume() -> None:
    for rel in AGENT_NODES:
        source = _read(rel)
        assert 'configurable.get("hitl_resume")' in source, rel
        assert "Command(resume=" in source, rel
