"""延迟工具恢复顺序：跨重启保持与在线追加顺序一致。

工具列表是 provider 提示词缓存前缀的一部分——恢复路径若重排（如 sorted），
重启后首个请求的 tools 前缀就与重启前的线上顺序不一致，造成整段缓存失效。
"""

from __future__ import annotations

from pathlib import Path

from src.infra.tool.deferred_manager import merge_discovered_names


def test_merge_preserves_restored_order_then_appends_in_memory_only() -> None:
    merged = merge_discovered_names(["zebra", "alpha"], ["alpha", "gamma", "zebra"])
    assert merged == ["zebra", "alpha", "gamma"]


def test_merge_with_empty_restored_keeps_in_memory_order() -> None:
    assert merge_discovered_names([], ["b", "a"]) == ["b", "a"]


def test_merge_with_empty_in_memory_returns_restored_as_is() -> None:
    assert merge_discovered_names(["b", "a"], []) == ["b", "a"]


def test_merge_never_sorts() -> None:
    # 顺序就是语义：排序会与在线发现顺序不一致
    assert merge_discovered_names(["c", "a", "b"], []) == ["c", "a", "b"]


def test_both_contexts_use_the_shared_merge_helper() -> None:
    fast = Path("src/agents/fast_agent/context.py").read_text(encoding="utf-8")
    search = Path("src/agents/search_agent/context.py").read_text(encoding="utf-8")
    assert "merge_discovered_names(" in fast
    assert "merge_discovered_names(" in search
    # search 旧的 sorted 恢复路径必须移除（与在线追加顺序冲突）
    assert "sorted(\n                        set(pre_discovered)" not in search
