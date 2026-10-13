import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.infra.agent.middleware.persona_subagent import PersonaSubagentMiddleware


def request(subagent_type, *, result=None):
    messages = [HumanMessage(content="Research the topic")]
    if result is not None:
        messages.append(
            ToolMessage(
                content=json.dumps(result), name="search_persona_presets", tool_call_id="search-1"
            )
        )
    return ToolCallRequest(
        tool_call={
            "name": "task",
            "args": {"description": "Research", "subagent_type": subagent_type},
            "id": "task-1",
        },
        tool=None,
        state={"messages": messages},
        runtime=SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_discovered_role_replaces_task_with_trusted_subagent_tool():
    tool = object()
    build = AsyncMock(return_value=tool)
    handler = AsyncMock(return_value="done")
    middleware = PersonaSubagentMiddleware(build_task_tool=build)
    result = await middleware.awrap_tool_call(
        request("persona:p1", result={"success": True, "presets": [{"id": "p1"}]}), handler
    )
    assert result == "done"
    build.assert_awaited_once_with("p1")
    assert handler.await_args.args[0].tool is tool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "search_result",
    [None, {"error": "search unavailable"}, {"success": True, "presets": [{"id": "other"}]}],
)
async def test_unsearched_role_is_rejected(search_result):
    build = AsyncMock()
    handler = AsyncMock()
    result = await PersonaSubagentMiddleware(build_task_tool=build).awrap_tool_call(
        request("persona:p1", result=search_result), handler
    )
    assert result.status == "error"
    build.assert_not_awaited()
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_failure_does_not_enable_generic_fallback():
    handler = AsyncMock()
    result = await PersonaSubagentMiddleware(build_task_tool=AsyncMock()).awrap_tool_call(
        request("general-purpose", result={"error": "permission denied"}), handler
    )
    assert result.status == "error"
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_latest_search_failure_blocks_earlier_successful_fallback():
    req = request("general-purpose", result={"success": True, "presets": []})
    req.state["messages"].append(
        ToolMessage(
            content=json.dumps({"error": "permission denied"}),
            name="search_persona_presets",
            tool_call_id="search-2",
        )
    )
    handler = AsyncMock()
    result = await PersonaSubagentMiddleware(build_task_tool=AsyncMock()).awrap_tool_call(
        req, handler
    )
    assert result.status == "error"
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_successful_search_allows_generic_fallback():
    handler = AsyncMock(return_value="done")
    result = await PersonaSubagentMiddleware(build_task_tool=AsyncMock()).awrap_tool_call(
        request("general-purpose", result={"success": True, "presets": []}), handler
    )
    assert result == "done"


@pytest.mark.asyncio
async def test_role_loading_failure_does_not_dispatch_generic():
    handler = AsyncMock()
    result = await PersonaSubagentMiddleware(
        build_task_tool=AsyncMock(side_effect=ValueError("private details"))
    ).awrap_tool_call(
        request("persona:p1", result={"success": True, "presets": [{"id": "p1"}]}), handler
    )
    assert result.status == "error"
    assert "private details" not in result.content
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_role_load_requires_new_search_before_generic_fallback():
    req = request("persona:p1", result={"success": True, "presets": [{"id": "p1"}]})
    middleware = PersonaSubagentMiddleware(build_task_tool=AsyncMock(side_effect=PermissionError()))
    failure = await middleware.awrap_tool_call(req, AsyncMock())
    req.state["messages"].append(failure)
    req.tool_call["args"]["subagent_type"] = "general-purpose"
    handler = AsyncMock()
    result = await middleware.awrap_tool_call(req, handler)
    assert result.status == "error"
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_previous_user_turn_search_does_not_authorize_new_dispatch():
    req = request("persona:p1", result={"success": True, "presets": [{"id": "p1"}]})
    req.state["messages"].append(HumanMessage(content="A different task"))
    result = await PersonaSubagentMiddleware(build_task_tool=AsyncMock()).awrap_tool_call(
        req, AsyncMock()
    )
    assert result.status == "error"


@pytest.mark.asyncio
async def test_sdk_dispatches_discovered_role_with_its_system_prompt():
    from deepagents import create_deep_agent
    from deepagents.backends import StateBackend
    from deepagents.middleware.subagents import SubAgentMiddleware
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool

    from src.infra.agent.middleware.prompt_injection import SectionPromptMiddleware
    from tests.agents.core.test_fork_subagent_contract import _ScriptedChatModel

    @tool
    def search_persona_presets(query: str) -> str:
        """Find a role."""
        return json.dumps({"success": True, "presets": [{"id": "p1"}]})

    parent = _ScriptedChatModel(
        script=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "search_persona_presets",
                        "args": {"query": "research"},
                        "id": "search-1",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {"description": "Research", "subagent_type": "persona:p1"},
                        "id": "task-1",
                    }
                ],
            ),
            AIMessage(content="synthesis"),
        ]
    )
    child = _ScriptedChatModel(script=[AIMessage(content="role executed")])
    backend = StateBackend()

    async def build_task_tool(preset_id):
        assert preset_id == "p1"
        return SubAgentMiddleware(
            backend=backend,
            subagents=[
                {
                    "name": "persona:p1",
                    "description": "Researcher",
                    "model": child,
                    "tools": [],
                    "system_prompt": "Scoped subagent",
                    "middleware": [SectionPromptMiddleware(sections=["TRUSTED_ROLE_PROMPT"])],
                }
            ],
        ).tools[0]

    graph = create_deep_agent(
        model=parent,
        backend=backend,
        tools=[search_persona_presets],
        middleware=[PersonaSubagentMiddleware(build_task_tool=build_task_tool)],
    )
    result = await graph.ainvoke({"messages": [HumanMessage(content="Research")]})
    assert result["messages"][-1].content == "synthesis"
    assert child.calls
    assert "TRUSTED_ROLE_PROMPT" in str(child.calls[0][0].content)
    assert any(
        isinstance(message, ToolMessage) and "role executed" in str(message.content)
        for message in result["messages"]
    )
