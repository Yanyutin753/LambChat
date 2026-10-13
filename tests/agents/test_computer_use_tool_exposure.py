"""computer_use 工具注册与会话级暴露守门。

暴露链路:FastAgentContext.setup 注册(get_tools 只做 MCP 懒加载,不装配
基础工具——漏调 setup 的测试会拿到空表,这是已知坑而非工具缺失)。
fast、team、search 在 setup 注册，并在创建图前按本地在线机器过滤。
quick 是纯 LLM 无工具设计,不适用。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.agents.fast_agent.context import FastAgentContext
from src.agents.search_agent.context import SearchAgentContext

CONTEXT_CLASSES = [FastAgentContext, SearchAgentContext]


def test_all_agent_modes_gate_desktop_tools_before_graph_creation() -> None:
    for mode in ("fast_agent", "search_agent", "team_agent"):
        source = Path(f"src/agents/{mode}/nodes.py").read_text()
        assert source.index(
            "filter_computer_use_tools(prepared.tools, computer_use_context)"
        ) < source.index("create_deep_agent(")
        assert "computer_use_context=computer_use_context" in source
        if mode != "team_agent":
            assert (
                "filter_computer_use_tools(\n                list(fresh_context.filter_tools())"
                in source
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("context_class", CONTEXT_CLASSES)
async def test_computer_use_exposed_inline_after_setup(context_class) -> None:
    context = context_class(user_id="cua-exposure-test")
    try:
        await context.setup()
        tools = await context.get_tools()
        names = [getattr(t, "name", "?") for t in tools]
        assert "computer_use" in names

        filtered = context.filter_tools()
        assert any(getattr(t, "name", "") == "computer_use" for t in filtered)
    finally:
        await context.close()


@pytest.mark.asyncio
async def test_computer_use_tool_doc_carries_no_osascript_rule() -> None:
    """工具描述内嵌禁 osascript 铁律(agent 的使用指引载体)。"""
    context = FastAgentContext(user_id="cua-exposure-test")
    try:
        await context.setup()
        tools = await context.get_tools()
        tool = next(t for t in tools if getattr(t, "name", "") == "computer_use")
        assert "osascript" in tool.description
        assert "NEVER" in tool.description
    finally:
        await context.close()
