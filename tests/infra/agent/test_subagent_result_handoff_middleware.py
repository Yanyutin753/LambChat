from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from src.infra.agent.middleware.subagent_result_handoff import (
    SubagentResultHandoffMiddleware,
)


@pytest.mark.asyncio
async def test_subagent_result_handoff_writes_task_command_message_to_file() -> None:
    writes: list[tuple[str, str]] = []

    class _Backend:
        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=f"/workflow/session{path}")

    middleware = SubagentResultHandoffMiddleware(
        backend=_Backend(),
        run_id_factory=lambda: "report123",
    )
    request = SimpleNamespace(
        runtime=object(),
        tool_call={
            "id": "call-1",
            "name": "task",
            "args": {
                "subagent_type": "codebase-investigator",
                "description": "Inspect auth flow.",
            },
        },
    )

    async def _handler(_request: Any) -> Command:
        return Command(
            update={
                "messages": [ToolMessage("Found auth.py issue.", tool_call_id="call-1")],
                "other_state": "preserved",
            }
        )

    result = await middleware.awrap_tool_call(request, _handler)

    assert len(writes) == 1
    path, content = writes[0]
    assert path == "/subagent_reports/subagent_report_report123.md"
    assert "Subagent Report" in content
    assert "codebase-investigator" in content
    assert "Inspect auth flow." in content
    assert "Found auth.py issue." in content
    assert isinstance(result, Command)
    assert result.update["other_state"] == "preserved"
    returned_message = result.update["messages"][0]
    assert isinstance(returned_message, ToolMessage)
    assert returned_message.tool_call_id == "call-1"
    assert returned_message.additional_kwargs["lambchat_original_content"] == "Found auth.py issue."
    assert (
        "Subagent report saved to: /workflow/session/subagent_reports/subagent_report_report123.md"
        in returned_message.content
    )
    assert "Found auth.py issue." not in returned_message.content


@pytest.mark.asyncio
async def test_subagent_result_handoff_uses_backend_work_dir() -> None:
    writes: list[tuple[str, str]] = []

    class _DefaultBackend:
        work_dir = "/sandbox/sessions/session-1"

    class _Backend:
        default = _DefaultBackend()

        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=path)

    middleware = SubagentResultHandoffMiddleware(
        backend=_Backend(),
        run_id_factory=lambda: "sandbox",
    )
    request = SimpleNamespace(
        runtime=object(),
        tool_call={
            "id": "call-1",
            "name": "task",
            "args": {"subagent_type": "general-purpose", "description": "Work."},
        },
    )

    async def _handler(_request: Any) -> ToolMessage:
        return ToolMessage("Sandbox report.", tool_call_id="call-1")

    result = await middleware.awrap_tool_call(request, _handler)

    assert len(writes) == 1
    assert writes[0][0] == "/sandbox/sessions/session-1/subagent_reports/subagent_report_sandbox.md"
    assert isinstance(result, ToolMessage)
    assert (
        "Subagent report saved to: "
        "/sandbox/sessions/session-1/subagent_reports/subagent_report_sandbox.md"
    ) in result.content


@pytest.mark.asyncio
async def test_subagent_result_handoff_leaves_non_task_tools_unchanged() -> None:
    class _Backend:
        async def awrite(self, _path: str, _content: str):
            raise AssertionError("non-task tools should not write handoff files")

    middleware = SubagentResultHandoffMiddleware(backend=_Backend())
    request = SimpleNamespace(
        runtime=object(),
        tool_call={"id": "call-1", "name": "read_file", "args": {}},
    )

    async def _handler(_request: Any) -> ToolMessage:
        return ToolMessage("file content", tool_call_id="call-1")

    result = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(result, ToolMessage)
    assert result.content == "file content"


@pytest.mark.asyncio
async def test_subagent_activity_log_reference_is_preserved_in_report_file() -> None:
    writes: list[tuple[str, str]] = []

    class _Backend:
        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=path)

    middleware = SubagentResultHandoffMiddleware(
        backend=_Backend(),
        run_id_factory=lambda: "withactivity",
    )
    request = SimpleNamespace(
        runtime=object(),
        tool_call={
            "id": "call-1",
            "name": "task",
            "args": {"subagent_type": "general-purpose", "description": "Work."},
        },
    )

    async def _handler(_request: Any) -> ToolMessage:
        return ToolMessage(
            "Final answer.\n\n[Activity log saved to: /subagent_activity/activity_abc.md]",
            tool_call_id="call-1",
        )

    result = await middleware.awrap_tool_call(request, _handler)

    assert len(writes) == 1
    assert "[Activity log saved to: /subagent_activity/activity_abc.md]" in writes[0][1]
    assert isinstance(result, ToolMessage)
    assert "Subagent report saved to: /subagent_reports/subagent_report_withactivity.md" in str(
        result.content
    )
    assert "Activity log saved to: /subagent_activity/activity_abc.md" in str(result.content)
