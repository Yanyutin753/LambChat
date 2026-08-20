"""结构测试：所有提供 ask_human 工具的 agent 节点都必须在流式执行时
设置 hitl_interrupt_supported，否则 interrupt 模式下 ask_human 会直接抛错。"""

from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"


def _read(rel: str) -> str:
    return (SRC / rel).read_text(encoding="utf-8")


def test_fast_agent_node_sets_hitl_interrupt_flag() -> None:
    source = _read("agents/fast_agent/nodes.py")
    assert "hitl_interrupt_supported.set" in source


def test_search_agent_node_sets_hitl_interrupt_flag() -> None:
    source = _read("agents/search_agent/nodes.py")
    assert "hitl_interrupt_supported.set" in source


def test_team_agent_node_sets_hitl_interrupt_flag() -> None:
    source = _read("agents/team_agent/nodes.py")
    assert "hitl_interrupt_supported.set" in source
