from __future__ import annotations

import pytest
from langchain_core.tools import BaseTool

from src.infra.tool import internal_registry
from src.kernel.schemas.mcp import MCPToolPolicy


class _FakeTool(BaseTool):
    name: str
    description: str = ""

    def _run(self, *args, **kwargs):
        return "sync"

    async def _arun(self, *args, **kwargs):
        return "async"


@pytest.mark.asyncio
async def test_internal_registry_splits_inline_and_deferred_tools(monkeypatch) -> None:
    tools = [
        _FakeTool(name="inline_tool", description="Inline"),
        _FakeTool(name="deferred_tool", description="Deferred"),
        _FakeTool(name="default_tool", description="Defaults to deferred"),
    ]

    async def policies():
        return {
            "inline_tool": MCPToolPolicy(
                server_name="lambchat_internal",
                tool_name="inline_tool",
                inline_exposure=True,
            ),
            "deferred_tool": MCPToolPolicy(
                server_name="lambchat_internal",
                tool_name="deferred_tool",
                inline_exposure=False,
            ),
        }

    monkeypatch.setattr(internal_registry, "build_internal_tools", lambda: tools)
    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", policies)

    direct, deferred = await internal_registry.get_internal_tools_by_exposure_for_user(
        user_id="user-1",
        user_roles=[],
        is_admin=False,
    )

    assert [tool.name for tool in direct] == ["inline_tool"]
    assert [tool.name for tool in deferred] == ["deferred_tool", "default_tool"]


@pytest.mark.asyncio
async def test_aggregate_internal_registry_remains_backward_compatible(monkeypatch) -> None:
    tools = [_FakeTool(name="one"), _FakeTool(name="two")]

    async def no_policies():
        return {}

    monkeypatch.setattr(internal_registry, "build_internal_tools", lambda: tools)
    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_policies)

    aggregate = await internal_registry.get_internal_tools_for_user(
        user_id="user-1",
        user_roles=[],
        is_admin=False,
    )

    assert [tool.name for tool in aggregate] == ["one", "two"]
