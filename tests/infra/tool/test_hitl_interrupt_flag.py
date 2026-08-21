"""hitl_interrupt_supported 判定辅助函数测试。"""

from langgraph.checkpoint.memory import MemorySaver

from src.infra.tool.human_tool.runtime import interrupt_supported_for_checkpointer


class _PersistentCheckpointer:
    """任意持久 checkpointer 替身。"""


def test_none_checkpointer_disables_interrupt_mode() -> None:
    assert interrupt_supported_for_checkpointer(None) is False


def test_memory_saver_enables_interrupt_mode_in_current_process() -> None:
    assert interrupt_supported_for_checkpointer(MemorySaver()) is True


def test_persistent_checkpointer_enables_interrupt_mode() -> None:
    assert interrupt_supported_for_checkpointer(_PersistentCheckpointer()) is True
