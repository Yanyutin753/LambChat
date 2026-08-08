from __future__ import annotations

import gc

from src.infra.tool import tool_search


class _FakeTool:
    def __init__(
        self,
        idx: int,
        *,
        name: str | None = None,
        description: str | None = None,
        server: str = "server",
    ) -> None:
        self.name = name or f"server:tool_{idx}"
        self.description = description or f"Tool {idx} for cache cleanup testing"
        self.server = server


def test_search_tools_matches_mcp_and_system_tools_by_pinyin() -> None:
    tools = [
        _FakeTool(1, name="小红书发布", description="发布图文内容"),
        _FakeTool(
            2,
            name="publish_content",
            description="发布小红书内容",
            server="",
        ),
    ]

    full_pinyin = tool_search.search_tools_with_keywords("xiaohongshu", tools)
    initials = tool_search.search_tools_with_keywords("xhsfb", tools)

    assert {result.name for result in full_pinyin} == {"小红书发布", "publish_content"}
    assert [result.name for result in initials] == ["小红书发布"]


def test_parse_cache_does_not_retain_transient_tool_objects() -> None:
    tool_search._parse_cache.clear()

    tools = [_FakeTool(i) for i in range(50)]
    results = tool_search.search_tools_with_keywords("tool", tools, max_results=100)

    assert len(results) == 50
    assert len(tool_search._parse_cache) == 50

    del results
    del tools
    gc.collect()

    assert len(tool_search._parse_cache) == 0
