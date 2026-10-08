"""computer_use 工具的 agent 暴露守门:setup 后必须内联可见且不被过滤。

暴露链路:FastAgentContext.setup 注册(get_tools 只做 MCP 懒加载,不装配
基础工具——漏调 setup 的测试会拿到空表,这是已知坑而非工具缺失)。
所有支持本地沙箱的 agent 都必须暴露该工具:fast(直注册)、team(继承
FastAgentContext)、search(自有 context,须单独注册)。quick 是纯 LLM
无工具设计,不适用。
"""

from __future__ import annotations

import pytest

from src.agents.fast_agent.context import FastAgentContext
from src.agents.search_agent.context import SearchAgentContext

CONTEXT_CLASSES = [FastAgentContext, SearchAgentContext]


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
