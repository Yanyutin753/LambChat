from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage, ToolMessage

from src.infra.agent.middleware import (
    SubagentExecutionPolicyMiddleware,
    TaskDelegationEnvelopeMiddleware,
    TeamRouterDelegationGuardMiddleware,
)


def _request(name: str, args: dict | None = None, messages: list | None = None):
    return SimpleNamespace(
        tool_call={"id": "call-1", "name": name, "args": args or {}},
        state={"messages": messages or [HumanMessage(content="Please inspect the project.")]},
    )


@pytest.mark.asyncio
async def test_team_router_direct_work_tool_is_nudged_before_delegation() -> None:
    middleware = TeamRouterDelegationGuardMiddleware()
    called = False

    async def handler(_request):
        nonlocal called
        called = True
        return ToolMessage(content="ok", tool_call_id="call-1", name="read_file")

    result = await middleware.awrap_tool_call(_request("read_file"), handler)

    assert called is False
    assert isinstance(result, ToolMessage)
    assert "active team members should be used first" in result.content


@pytest.mark.asyncio
async def test_team_router_task_call_requires_structured_envelope() -> None:
    middleware = TaskDelegationEnvelopeMiddleware()
    called = False

    async def handler(_request):
        nonlocal called
        called = True
        return ToolMessage(content="ok", tool_call_id="call-1", name="task")

    result = await middleware.awrap_tool_call(
        _request("task", {"description": "Write a short slogan."}),
        handler,
    )

    assert called is False
    assert isinstance(result, ToolMessage)
    assert "structured task brief required" in result.content


@pytest.mark.asyncio
async def test_subagent_text_only_assignment_blocks_artifact_tool_once() -> None:
    middleware = SubagentExecutionPolicyMiddleware()
    messages = [
        HumanMessage(
            content=(
                "Task type: TEXT_ONLY\n"
                "Delivery mode: RETURN_TEXT\n"
                "Reference policy: USER_PROVIDED_ONLY\n"
                "Tool policy: NO_TOOLS\n"
                "Objective: Write three prompts."
            )
        )
    ]
    called = False

    async def handler(_request):
        nonlocal called
        called = True
        return ToolMessage(content="ok", tool_call_id="call-1", name="write_file")

    result = await middleware.awrap_tool_call(_request("write_file", messages=messages), handler)

    assert called is False
    assert isinstance(result, ToolMessage)
    assert "outside the assigned policy" in result.content
