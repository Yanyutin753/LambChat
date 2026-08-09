import json
from types import SimpleNamespace

import pytest
from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage

from src.infra.agent.middleware.tool_interception import ToolSearchMiddleware
from src.infra.session.conversation_history import (
    ConversationHistoryInvalidArgumentError,
    ConversationHistoryNotFoundError,
)
from src.infra.tool import conversation_history_tool as history_tools
from src.infra.tool.deferred_manager import DeferredToolManager
from src.infra.tool.mcp_client import MCPToolWithRetry


class _Runtime:
    def __init__(self, user_id: str | None) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {"configurable": {"context": context}}


@pytest.mark.asyncio
async def test_search_tool_injects_user_and_returns_paginated_json(monkeypatch) -> None:
    calls = []

    class _Service:
        async def search(self, user_id, query, limit=10, cursor=None):
            calls.append((user_id, query, limit, cursor))
            return {"success": True, "items": [], "next_cursor": None}

    monkeypatch.setattr(history_tools, "ConversationHistoryService", _Service)
    result = json.loads(
        await history_tools.search_conversation_history.coroutine(
            "parser",
            5,
            "cursor-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert calls == [("user-1", "parser", 5, "cursor-1")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ConversationHistoryInvalidArgumentError("bad"), "invalid_argument"),
        (ConversationHistoryNotFoundError("missing"), "not_found"),
        (RuntimeError("database body must not leak"), "temporarily_unavailable"),
    ],
)
async def test_detail_tool_returns_stable_error_categories(monkeypatch, error, expected) -> None:
    class _Service:
        async def get_detail(self, *args, **kwargs):
            raise error

    monkeypatch.setattr(history_tools, "ConversationHistoryService", _Service)
    result = json.loads(
        await history_tools.get_conversation_detail.coroutine(
            "session-1",
            "run-1",
            runtime=_Runtime("user-1"),
        )
    )

    assert result == {"success": False, "error": expected}
    assert "database body" not in json.dumps(result)


@pytest.mark.asyncio
async def test_history_tools_require_authenticated_runtime() -> None:
    search_result = json.loads(
        await history_tools.search_conversation_history.coroutine(
            "parser",
            runtime=_Runtime(None),
        )
    )
    detail_result = json.loads(
        await history_tools.get_conversation_detail.coroutine(
            "session-1",
            runtime=_Runtime(None),
        )
    )

    assert search_result == {"success": False, "error": "not_authenticated"}
    assert detail_result == {"success": False, "error": "not_authenticated"}


def test_history_tool_factory_returns_both_tools() -> None:
    assert [tool.name for tool in history_tools.get_conversation_history_tools()] == [
        "search_conversation_history",
        "get_conversation_detail",
    ]


def test_history_tool_descriptions_embed_the_lookup_sop() -> None:
    search_description = history_tools.search_conversation_history.description
    detail_description = history_tools.get_conversation_detail.description

    assert "SOP" in search_description
    assert "get_conversation_detail" in search_description
    assert "next_cursor" in search_description
    assert "SOP" in detail_description
    assert "search_conversation_history" in detail_description
    assert "memory_recall" in detail_description
    assert "source_refs" in detail_description


@pytest.mark.asyncio
async def test_search_history_runs_through_internal_mcp_wrapper(monkeypatch) -> None:
    calls = []

    class _Service:
        async def search(self, user_id, query, limit=10, cursor=None):
            calls.append((user_id, query, limit, cursor))
            return {"success": True, "items": [], "next_cursor": None}

    monkeypatch.setattr(history_tools, "ConversationHistoryService", _Service)
    wrapped = MCPToolWithRetry(
        history_tools.search_conversation_history,
        max_retries=1,
        user_id="user-1",
        server_name="lambchat_internal",
    )
    runtime = ToolRuntime(
        state={},
        context=None,
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}},
        stream_writer=lambda _value: None,
        tool_call_id="tool-call-1",
        store=None,
        tools=[],
    )

    result = json.loads(
        await wrapped.ainvoke(
            {"query": "自我介绍", "limit": 10, "runtime": runtime},
        )
    )

    assert result["success"] is True
    assert calls == [("user-1", "自我介绍", 10, None)]


@pytest.mark.asyncio
async def test_deferred_search_history_receives_agent_tool_runtime(monkeypatch) -> None:
    calls = []

    class _Service:
        async def search(self, user_id, query, limit=10, cursor=None):
            calls.append((user_id, query, limit, cursor))
            return {"success": True, "items": [], "next_cursor": None}

    monkeypatch.setattr(history_tools, "ConversationHistoryService", _Service)
    wrapped = MCPToolWithRetry(
        history_tools.search_conversation_history,
        max_retries=1,
        user_id="user-1",
        server_name="lambchat_internal",
    )
    manager = DeferredToolManager(
        all_deferred_tools=[],
        deferred_system_tools=[wrapped],
        session_id="session-1",
        pre_discovered_names=["search_conversation_history"],
    )
    middleware = ToolSearchMiddleware(deferred_manager=manager)
    runtime = ToolRuntime(
        state={},
        context=None,
        config={"configurable": {"context": SimpleNamespace(user_id="user-1")}},
        stream_writer=lambda _value: None,
        tool_call_id="tool-call-1",
        store=None,
        tools=[],
    )
    request = SimpleNamespace(
        tool_call={
            "name": "search_conversation_history",
            "id": "tool-call-1",
            "args": {"query": "介绍 自己 信息", "limit": 10},
        },
        tool=None,
        runtime=runtime,
    )

    async def _handler(_request):
        raise AssertionError("discovered deferred tool should execute directly")

    result = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(result, ToolMessage)
    assert json.loads(result.content)["success"] is True
    assert calls == [("user-1", "介绍 自己 信息", 10, None)]
