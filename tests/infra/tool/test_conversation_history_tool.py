import json
from types import SimpleNamespace

import pytest

from src.infra.session.conversation_history import (
    ConversationHistoryInvalidArgumentError,
    ConversationHistoryNotFoundError,
)
from src.infra.tool import conversation_history_tool as history_tools


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
