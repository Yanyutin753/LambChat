from unittest.mock import AsyncMock, Mock

import pytest

from src.infra.agent.events.tool_events import ToolEventMixin


@pytest.mark.parametrize(
    "item",
    [
        {"content": "task"},
        {"content": "task", "status": "unknown"},
        {"content": "task", "status": ["pending"]},
        {"status": "pending"},
        None,
    ],
)
async def test_invalid_todos_are_not_published(item):
    processor = ToolEventMixin()
    processor.presenter = Mock()
    processor._presenter_emit = AsyncMock()
    await processor._handle_tool_start(
        {"data": {"input": {"todos": [item]}}, "run_id": "test"},
        "write_todos",
        "search",
        0,
    )
    processor.presenter.present_todo.assert_not_called()


async def test_valid_todos_preserve_agent_scope():
    processor = ToolEventMixin()
    processor.presenter = Mock()
    processor._presenter_emit = AsyncMock()
    todos = [{"content": "task", "status": "pending"}]
    await processor._handle_tool_start(
        {"data": {"input": {"todos": todos}}, "run_id": "test"},
        "write_todos",
        "child",
        1,
    )
    processor.presenter.present_todo.assert_called_once_with(todos, depth=1, agent_id="child")
