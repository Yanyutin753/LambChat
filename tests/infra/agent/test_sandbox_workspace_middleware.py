"""Tests for SandboxWorkspaceMiddleware (workspace path on file-tool descriptions)."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from src.infra.agent.middleware.sandbox_workspace import SandboxWorkspaceMiddleware


class _FakeTool(BaseTool):
    name: str = "ls"
    description: str = "Lists all files in a directory."

    def _run(self, *args, **kwargs):  # pragma: no cover - test stub
        return "ok"


class _OtherTool(BaseTool):
    name: str = "web_search"
    description: str = "Search the web."

    def _run(self, *args, **kwargs):  # pragma: no cover - test stub
        return "ok"


class _Request:
    def __init__(self, tools=None, system_message=None) -> None:
        self.messages = []
        self.system_message = system_message or SystemMessage(content="base")
        self.tools = tools if tools is not None else [_FakeTool(), _OtherTool()]

    def override(self, **kwargs):
        req = _Request(
            tools=kwargs.get("tools", self.tools),
            system_message=kwargs.get("system_message", self.system_message),
        )
        return req


async def _handler(request):
    return request


async def test_workspace_policy_lands_on_file_tool_description() -> None:
    middleware = SandboxWorkspaceMiddleware(
        policy_text="## Sandbox Runtime\n\nCurrent session workspace: `/w/sessions/abc`"
    )
    result = await middleware.awrap_model_call(_Request(), _handler)
    ls = next(t for t in result.tools if t.name == "ls")
    assert "<sandbox_workspace_context>" in ls.description
    assert "/w/sessions/abc" in ls.description
    # Other tools untouched; system prompt untouched.
    web = next(t for t in result.tools if t.name == "web_search")
    assert "<sandbox_workspace_context>" not in web.description
    assert result.system_message.content == "base"


async def test_workspace_policy_falls_back_to_system_tail_without_file_tools() -> None:
    middleware = SandboxWorkspaceMiddleware(policy_text="workspace: /w/sessions/abc")
    result = await middleware.awrap_model_call(_Request(tools=[_OtherTool()]), _handler)
    assert "<sandbox_workspace_context>" in str(result.system_message.content)


async def test_empty_policy_is_a_noop() -> None:
    middleware = SandboxWorkspaceMiddleware(policy_text="  ")
    request = _Request()
    result = await middleware.awrap_model_call(request, _handler)
    assert result is request


async def test_framing_is_idempotent() -> None:
    middleware = SandboxWorkspaceMiddleware(policy_text="workspace: /w/abc")
    first = await middleware.awrap_model_call(_Request(), _handler)
    second = await middleware.awrap_model_call(first, _handler)
    ls = next(t for t in second.tools if t.name == "ls")
    assert ls.description.count("<sandbox_workspace_context>") == 1
