"""Keep provider-generated Todo descriptions compatible with the canonical state."""

import copy
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.agents.core.todo_middleware import create_todo_middleware


@pytest.mark.parametrize("async_call", [False, True])
async def test_description_todos_pass_tool_validation_and_update_canonical_state(async_call):
    tool = create_todo_middleware().tools[0]
    arguments = {
        "todos": [
            {"description": "梳理法律人转行赛道", "id": "1", "status": "in_progress"},
            {"description": "撰写图文笔记", "id": "2", "status": "pending"},
            {"description": "整理图片文字", "id": "3", "status": "pending"},
        ]
    }
    original = copy.deepcopy(arguments)
    parsed = tool._parse_input(arguments, "todo-call")
    runtime = SimpleNamespace(tool_call_id="todo-call")
    if async_call:
        result = await tool.coroutine(runtime=runtime, **parsed)
    else:
        result = tool.func(runtime=runtime, **parsed)
    assert result.update["todos"] == [
        {"content": item["description"], "status": item["status"]} for item in original["todos"]
    ]
    assert result.update["messages"][0].tool_call_id == "todo-call"
    assert arguments == original


def test_explicit_content_wins_over_description():
    tool = create_todo_middleware().tools[0]
    parsed = tool._parse_input(
        {"todos": [{"content": "keep", "description": "do not overwrite", "status": "completed"}]},
        "todo-call",
    )
    assert parsed == {"todos": [{"content": "keep", "status": "completed"}]}


@pytest.mark.parametrize(
    "item",
    [
        {"description": 123, "status": "pending"},
        {"description": "step", "status": "done"},
        {"content": None, "description": "must not hide invalid content", "status": "pending"},
        {"status": "pending"},
    ],
)
def test_todo_compatibility_does_not_accept_invalid_tasks(item):
    tool = create_todo_middleware().tools[0]
    with pytest.raises(ValidationError):
        tool._parse_input({"todos": [item]}, "todo-call")


def test_todo_tool_description_names_required_content_field():
    assert "`content`" in create_todo_middleware().tool_description
