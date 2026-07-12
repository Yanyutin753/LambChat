from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.infra.agent.middleware.subagent_activity import SubagentActivityMiddleware


@pytest.mark.asyncio
async def test_subagent_activity_middleware_writes_log_and_appends_reference_to_final_response() -> (
    None
):
    writes: list[tuple[str, str]] = []

    class _DefaultBackend:
        work_dir = "/sandbox/session-a"

    class _Backend:
        default = _DefaultBackend()

        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=path)

    middleware = SubagentActivityMiddleware(
        backend=_Backend(),
        run_id_factory=lambda: "activity123",
    )

    async def _tool_handler(_request: Any) -> ToolMessage:
        return ToolMessage("auth.py contains the check", tool_call_id="tool-1")

    await middleware.awrap_tool_call(
        SimpleNamespace(
            runtime=object(),
            tool_call={"name": "read_file", "args": {"file_path": "auth.py"}},
        ),
        _tool_handler,
    )

    async def _model_handler(_request: Any) -> AIMessage:
        return AIMessage(content="Final report", tool_calls=[])

    result = await middleware.awrap_model_call(SimpleNamespace(runtime=object()), _model_handler)

    assert len(writes) == 1
    path, content = writes[0]
    assert path == "/sandbox/session-a/subagent_activity/activity_activity123.md"
    assert "Tool: read_file" in content
    assert "auth.py contains the check" in content
    assert isinstance(result, AIMessage)
    assert "Final report" in str(result.content)
    assert (
        "[Activity log saved to: /sandbox/session-a/subagent_activity/activity_activity123.md]"
        in str(result.content)
    )


@pytest.mark.asyncio
async def test_subagent_activity_middleware_skips_log_for_final_response_without_prior_activity() -> (
    None
):
    writes: list[tuple[str, str]] = []

    class _Backend:
        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=path)

    middleware = SubagentActivityMiddleware(
        backend=_Backend(),
        run_id_factory=lambda: "quiet",
    )

    async def _model_handler(_request: Any) -> AIMessage:
        return AIMessage(content="Direct final report", tool_calls=[])

    result = await middleware.awrap_model_call(SimpleNamespace(runtime=object()), _model_handler)

    assert writes == []
    assert isinstance(result, AIMessage)
    assert result.content == "Direct final report"


@pytest.mark.asyncio
async def test_subagent_activity_middleware_prefers_latest_state_messages_for_activity() -> None:
    writes: list[tuple[str, str]] = []

    class _Backend:
        async def awrite(self, path: str, content: str):
            writes.append((path, content))
            return SimpleNamespace(error=None, path=path)

    middleware = SubagentActivityMiddleware(
        backend=_Backend(),
        run_id_factory=lambda: "messages",
    )
    request = SimpleNamespace(
        runtime=object(),
        state={
            "messages": [
                HumanMessage(content="Investigate auth."),
                AIMessage(
                    content="I will inspect the file.",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "name": "read_file",
                            "args": {"file_path": "auth.py"},
                        }
                    ],
                ),
                ToolMessage("auth.py contains the check", tool_call_id="call-1"),
            ]
        },
    )

    async def _model_handler(_request: Any) -> AIMessage:
        return AIMessage(content="Final report should live only in report file", tool_calls=[])

    result = await middleware.awrap_model_call(request, _model_handler)

    assert len(writes) == 1
    _path, content = writes[0]
    assert "Investigate auth." in content
    assert "Tool calls: read_file" in content
    assert "auth.py contains the check" in content
    assert "Final report should live only in report file" not in content
    assert isinstance(result, AIMessage)
    assert "Activity log saved to: /subagent_activity/activity_messages.md" in str(result.content)
