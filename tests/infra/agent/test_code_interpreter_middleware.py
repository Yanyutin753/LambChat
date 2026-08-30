"""Tests for code interpreter middleware factory and REPL tool routing guidance."""

from __future__ import annotations

import sys
import types

from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool


def test_code_interpreter_middleware_disabled_when_global_setting_off(monkeypatch):
    from src.infra.agent.middleware.code_interpreter import create_code_interpreter_middleware
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "ENABLE_CODE_INTERPRETER", False, raising=False)

    middleware = create_code_interpreter_middleware({"enable_code_interpreter": True})

    assert middleware == []


def test_code_interpreter_middleware_disabled_when_agent_option_off(monkeypatch):
    from src.infra.agent.middleware.code_interpreter import create_code_interpreter_middleware
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "ENABLE_CODE_INTERPRETER", True, raising=False)

    middleware = create_code_interpreter_middleware({"enable_code_interpreter": False})

    assert middleware == []


def test_code_interpreter_middleware_created_when_both_switches_enabled(monkeypatch):
    from src.infra.agent.middleware.code_interpreter import (
        CodeInterpreterRoutingMiddleware,
        create_code_interpreter_middleware,
    )
    from src.kernel.config import settings

    class FakeCodeInterpreterMiddleware:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module = types.SimpleNamespace(CodeInterpreterMiddleware=FakeCodeInterpreterMiddleware)
    monkeypatch.setitem(sys.modules, "langchain_quickjs", fake_module)
    monkeypatch.setattr(settings, "ENABLE_CODE_INTERPRETER", True, raising=False)

    middleware = create_code_interpreter_middleware({"enable_code_interpreter": True})

    assert len(middleware) == 2
    assert isinstance(middleware[0], FakeCodeInterpreterMiddleware)
    assert middleware[0].kwargs == {}
    assert isinstance(middleware[1], CodeInterpreterRoutingMiddleware)


class _EvalTool(BaseTool):
    name: str = "eval"
    description: str = "Execute JavaScript in a sandboxed REPL."

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
        self.tools = tools if tools is not None else [_EvalTool(), _OtherTool()]

    def override(self, **kwargs):
        return _Request(
            tools=kwargs.get("tools", self.tools),
            system_message=kwargs.get("system_message", self.system_message),
        )


async def _handler(request):
    return request


async def test_routing_with_sandbox_directs_pure_computation_to_repl() -> None:
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(sandbox_active=True)
    result = await middleware.awrap_model_call(_Request(), _handler)

    eval_tool = next(t for t in result.tools if t.name == "eval")
    assert "<code_interpreter_routing>" in eval_tool.description
    assert "execute" in eval_tool.description
    assert "sandbox" in eval_tool.description.lower()
    # Original description preserved; other tools and system prompt untouched.
    assert eval_tool.description.startswith("Execute JavaScript in a sandboxed REPL.")
    other = next(t for t in result.tools if t.name == "web_search")
    assert "<code_interpreter_routing>" not in other.description
    assert result.system_message.content == "base"


async def test_routing_without_sandbox_does_not_mention_execute() -> None:
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(sandbox_active=False)
    result = await middleware.awrap_model_call(_Request(), _handler)

    eval_tool = next(t for t in result.tools if t.name == "eval")
    assert "<code_interpreter_routing>" in eval_tool.description
    assert "`execute`" not in eval_tool.description


async def test_routing_skips_when_eval_tool_absent() -> None:
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(sandbox_active=True)
    request = _Request(tools=[_OtherTool()])
    result = await middleware.awrap_model_call(request, _handler)

    assert result is request
    assert result.system_message.content == "base"


async def test_routing_is_idempotent() -> None:
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(sandbox_active=True)
    first = await middleware.awrap_model_call(_Request(), _handler)
    second = await middleware.awrap_model_call(first, _handler)
    eval_tool = next(t for t in second.tools if t.name == "eval")
    assert eval_tool.description.count("<code_interpreter_routing>") == 1
