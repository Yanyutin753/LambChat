"""Tests for SandboxSlowRunMiddleware (concept-first guidance on `execute`)."""

from __future__ import annotations

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from src.infra.agent.middleware.sandbox_slow_run import SandboxSlowRunMiddleware


class _ExecuteTool(BaseTool):
    name: str = "execute"
    description: str = "Executes a shell command in an isolated sandbox."

    def _run(self, *args, **kwargs):  # pragma: no cover - test stub
        return "ok"


class _OtherTool(BaseTool):
    name: str = "ls"
    description: str = "Lists all files in a directory."

    def _run(self, *args, **kwargs):  # pragma: no cover - test stub
        return "ok"


class _Request:
    def __init__(self, tools=None) -> None:
        self.messages = []
        self.system_message = SystemMessage(content="base")
        self.tools = tools if tools is not None else [_ExecuteTool(), _OtherTool()]

    def override(self, **kwargs):
        return _Request(tools=kwargs.get("tools", self.tools))


async def _handler(request):
    return request


async def test_guidance_lands_on_execute_description_only() -> None:
    middleware = SandboxSlowRunMiddleware()
    result = await middleware.awrap_model_call(_Request(), _handler)
    execute = next(t for t in result.tools if t.name == "execute")
    assert "<slow_sandbox_run_guidance>" in execute.description
    assert "conceptual answer as text BEFORE calling" in execute.description
    # 原描述保留在前，指引帧纯尾部追加
    assert execute.description.startswith("Executes a shell command")
    # 其它工具与 system prompt 不动
    ls = next(t for t in result.tools if t.name == "ls")
    assert "<slow_sandbox_run_guidance>" not in ls.description
    assert result.system_message.content == "base"


async def test_noop_without_execute_tool() -> None:
    middleware = SandboxSlowRunMiddleware()
    request = _Request(tools=[_OtherTool()])
    result = await middleware.awrap_model_call(request, _handler)
    assert result is request


async def test_framing_is_idempotent() -> None:
    middleware = SandboxSlowRunMiddleware()
    first = await middleware.awrap_model_call(_Request(), _handler)
    second = await middleware.awrap_model_call(first, _handler)
    execute = next(t for t in second.tools if t.name == "execute")
    assert execute.description.count("<slow_sandbox_run_guidance>") == 1
