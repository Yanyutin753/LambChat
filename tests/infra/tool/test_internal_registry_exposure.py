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


@pytest.mark.asyncio
async def test_conversation_history_tools_default_to_deferred_exposure(monkeypatch) -> None:
    monkeypatch.setattr(internal_registry.settings, "ENABLE_IMAGE_ANALYSIS", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_IMAGE_GENERATION", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_AUDIO_TRANSCRIPTION", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_SCHEDULED_TASK", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_WEB_SEARCH", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_WEB_FETCH", False)
    monkeypatch.setattr(internal_registry, "get_env_var_tools", lambda: [])
    monkeypatch.setattr(internal_registry, "get_persona_preset_tools", lambda: [])
    monkeypatch.setattr(internal_registry, "get_team_tools", lambda: [])

    async def no_policies():
        return {}

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_policies)

    direct, deferred = await internal_registry.get_internal_tools_by_exposure_for_user(
        user_id="user-1",
        user_roles=[],
        is_admin=False,
    )

    assert [tool.name for tool in direct] == []
    assert {tool.name for tool in deferred} == {
        "search_conversation_history",
        "get_conversation_detail",
    }


@pytest.mark.asyncio
async def test_web_tools_mount_by_default_as_system_tools(monkeypatch) -> None:
    """web_search/web_fetch 默认即挂载且 inline 直挂：无策略时进 direct
    暴露集（模型工具表直接可见），不再需要先经 tool_search 元工具发现；
    管理员显式设置过策略的以显式值为准。"""
    monkeypatch.setattr(internal_registry.settings, "ENABLE_IMAGE_ANALYSIS", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_IMAGE_GENERATION", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_AUDIO_TRANSCRIPTION", False)
    monkeypatch.setattr(internal_registry.settings, "ENABLE_SCHEDULED_TASK", False)
    monkeypatch.setattr(internal_registry, "get_env_var_tools", lambda: [])
    monkeypatch.setattr(internal_registry, "get_persona_preset_tools", lambda: [])
    monkeypatch.setattr(internal_registry, "get_team_tools", lambda: [])

    async def no_policies():
        return {}

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", no_policies)

    # 不 monkeypatch web 开关：默认值（True）下两工具必须在册且直挂
    direct, deferred = await internal_registry.get_internal_tools_by_exposure_for_user(
        user_id="user-1",
        user_roles=[],
        is_admin=False,
    )
    direct_names = {tool.name for tool in direct}
    assert {"web_search", "web_fetch"} <= direct_names
    assert not {"web_search", "web_fetch"} & {tool.name for tool in deferred}

    # 显式策略优先：管理员钉死 inline_exposure=False 时回落 deferred
    from src.kernel.schemas.mcp import MCPToolPolicy

    async def explicit_policies():
        return {
            "web_search": MCPToolPolicy(
                server_name=internal_registry.INTERNAL_MCP_SERVER_NAME,
                tool_name="web_search",
                inline_exposure=False,
            ),
        }

    monkeypatch.setattr(internal_registry, "get_internal_tool_policies", explicit_policies)
    direct, deferred = await internal_registry.get_internal_tools_by_exposure_for_user(
        user_id="user-1",
        user_roles=[],
        is_admin=False,
    )
    assert "web_search" not in {tool.name for tool in direct}
    assert "web_search" in {tool.name for tool in deferred}
    # 未被显式策略覆盖的 web_fetch 仍默认直挂
    assert "web_fetch" in {tool.name for tool in direct}
