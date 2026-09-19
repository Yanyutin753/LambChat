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
    from src.infra.agent.middleware import code_interpreter as ci
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware
    from src.kernel.config import settings

    class FakeCodeInterpreterMiddleware:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module = types.SimpleNamespace(CodeInterpreterMiddleware=FakeCodeInterpreterMiddleware)
    monkeypatch.setitem(sys.modules, "langchain_quickjs", fake_module)
    monkeypatch.setattr(settings, "ENABLE_CODE_INTERPRETER", True, raising=False)
    monkeypatch.setattr(settings, "CODE_INTERPRETER_PTC_TOOLS", "", raising=False)
    monkeypatch.setattr(settings, "CODE_INTERPRETER_SNAPSHOT_KEY", "", raising=False)
    monkeypatch.setattr(ci, "_jwt_secret_is_explicit", lambda: False)

    middleware = ci.create_code_interpreter_middleware({"enable_code_interpreter": True})

    assert len(middleware) == 2
    assert isinstance(middleware[0], FakeCodeInterpreterMiddleware)
    # subagents=False：不安装 JS task() 桥，也不注入 ~9.8k 的 JS 子代理编排教程。
    assert middleware[0].kwargs == {"subagents": False, "ptc": None, "snapshot_signing_key": None}
    assert isinstance(middleware[1], CodeInterpreterRoutingMiddleware)


async def test_subagent_orchestration_prompt_is_not_injected() -> None:
    from langchain_quickjs import CodeInterpreterMiddleware
    from pydantic import BaseModel

    class TaskArgs(BaseModel):
        description: str
        subagent_type: str

    class TaskTool(BaseTool):
        name: str = "task"
        description: str = "Dispatch a subagent."
        args_schema: type = TaskArgs

        def _run(self, *args, **kwargs):  # pragma: no cover - test stub
            return "ok"

    class EvalTool(BaseTool):
        name: str = "eval"
        description: str = "Execute JavaScript in a sandboxed REPL."

        def _run(self, *args, **kwargs):  # pragma: no cover - test stub
            return "ok"

    class Request:
        def __init__(self) -> None:
            self.messages = []
            self.system_message = SystemMessage(content="base")
            self.tools = [EvalTool(), TaskTool()]

        def override(self, **kwargs):
            request = Request()
            request.tools = kwargs.get("tools", self.tools)
            request.system_message = kwargs.get("system_message", self.system_message)
            return request

    async def handler(request):
        return request

    middleware = CodeInterpreterMiddleware(subagents=False)
    result = await middleware.awrap_model_call(Request(), handler)

    content = result.system_message.content
    injected = content[-1]["text"] if isinstance(content, list) else str(content)
    assert "### Interpreter" in injected
    assert "Dispatching Subagents" not in injected
    assert len(injected) < 1000


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


class _WebFetchTool(BaseTool):
    name: str = "web_fetch"
    description: str = "Fetch a web page."

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


# ---------------------------------------------------------------------------
# PTC allowlist (programmatic tool calling) + snapshot signing key
# ---------------------------------------------------------------------------


def _enable_interpreter(monkeypatch) -> None:
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "ENABLE_CODE_INTERPRETER", True, raising=False)


def test_factory_passes_ptc_allowlist_and_snapshot_key(monkeypatch):
    from src.infra.agent.middleware import code_interpreter as ci

    _enable_interpreter(monkeypatch)
    monkeypatch.setattr(
        ci.settings, "CODE_INTERPRETER_PTC_TOOLS", "web_search,web_fetch", raising=False
    )
    monkeypatch.setattr(ci.settings, "CODE_INTERPRETER_SNAPSHOT_KEY", "explicit-key", raising=False)

    class FakeCodeInterpreterMiddleware:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_module = types.SimpleNamespace(CodeInterpreterMiddleware=FakeCodeInterpreterMiddleware)
    monkeypatch.setitem(sys.modules, "langchain_quickjs", fake_module)

    middleware = ci.create_code_interpreter_middleware({"enable_code_interpreter": True})

    assert middleware[0].kwargs == {
        "subagents": False,
        "ptc": ["web_search", "web_fetch"],
        "snapshot_signing_key": "explicit-key",
        # PTC 聚合场景放宽结果截断上限。
        "max_result_chars": 8000,
    }
    assert isinstance(middleware[1], ci.CodeInterpreterRoutingMiddleware)
    assert middleware[1].ptc_tools == ["web_search", "web_fetch"]


def test_factory_disables_ptc_when_allowlist_empty(monkeypatch):
    from src.infra.agent.middleware import code_interpreter as ci

    _enable_interpreter(monkeypatch)
    monkeypatch.setattr(ci.settings, "CODE_INTERPRETER_PTC_TOOLS", "", raising=False)
    monkeypatch.setattr(ci.settings, "CODE_INTERPRETER_SNAPSHOT_KEY", "explicit-key", raising=False)

    class FakeCodeInterpreterMiddleware:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setitem(
        sys.modules,
        "langchain_quickjs",
        types.SimpleNamespace(CodeInterpreterMiddleware=FakeCodeInterpreterMiddleware),
    )

    middleware = ci.create_code_interpreter_middleware({"enable_code_interpreter": True})

    # PTC 关闭时不额外传 max_result_chars，维持上游 4000 默认。
    assert "max_result_chars" not in middleware[0].kwargs
    assert middleware[0].kwargs["ptc"] is None
    assert middleware[1].ptc_tools == []


def test_factory_normalizes_messy_ptc_allowlist(monkeypatch):
    from src.infra.agent.middleware import code_interpreter as ci

    _enable_interpreter(monkeypatch)
    monkeypatch.setattr(
        ci.settings,
        "CODE_INTERPRETER_PTC_TOOLS",
        " web_search ,, web_search , web_fetch ",
        raising=False,
    )
    monkeypatch.setattr(ci.settings, "CODE_INTERPRETER_SNAPSHOT_KEY", "", raising=False)
    monkeypatch.setattr(ci, "_jwt_secret_is_explicit", lambda: True)
    monkeypatch.setattr(ci.settings, "JWT_SECRET_KEY", "a" * 40, raising=False)

    class FakeCodeInterpreterMiddleware:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setitem(
        sys.modules,
        "langchain_quickjs",
        types.SimpleNamespace(CodeInterpreterMiddleware=FakeCodeInterpreterMiddleware),
    )

    middleware = ci.create_code_interpreter_middleware({"enable_code_interpreter": True})

    assert middleware[0].kwargs["ptc"] == ["web_search", "web_fetch"]
    # 空白/重复条目被规整，且去重保持首次出现顺序。


def test_parse_ptc_tools_strips_dedups_and_drops_empty() -> None:
    from src.infra.agent.middleware.code_interpreter import _parse_ptc_tools

    assert _parse_ptc_tools("web_search,web_fetch") == ["web_search", "web_fetch"]
    assert _parse_ptc_tools("  a ,, a , b ,") == ["a", "b"]
    assert _parse_ptc_tools("") == []
    assert _parse_ptc_tools("   ") == []


def test_ptc_bridge_name_is_camel_case() -> None:
    from src.infra.agent.middleware.code_interpreter import _ptc_bridge_name

    assert _ptc_bridge_name("web_search") == "webSearch"
    assert _ptc_bridge_name("web_fetch") == "webFetch"
    assert _ptc_bridge_name("tool_search") == "toolSearch"


def test_resolve_snapshot_key_prefers_explicit_setting() -> None:
    from src.infra.agent.middleware.code_interpreter import _resolve_snapshot_key

    assert _resolve_snapshot_key(explicit="k", jwt_secret="a" * 40) == "k"


def test_resolve_snapshot_key_derives_stably_from_jwt_secret() -> None:
    from src.infra.agent.middleware.code_interpreter import _resolve_snapshot_key

    first = _resolve_snapshot_key(explicit="", jwt_secret="a" * 40)
    second = _resolve_snapshot_key(explicit="", jwt_secret="a" * 40)
    other = _resolve_snapshot_key(explicit="", jwt_secret="b" * 40)

    assert first and first == second and first != other
    assert first != "a" * 40


def test_resolve_snapshot_key_is_none_without_stable_secret() -> None:
    from src.infra.agent.middleware.code_interpreter import _resolve_snapshot_key

    assert _resolve_snapshot_key(explicit="", jwt_secret=None) is None
    assert _resolve_snapshot_key(explicit="", jwt_secret="") is None


def test_generated_jwt_secret_is_not_treated_as_stable(monkeypatch) -> None:
    from src.infra.agent.middleware import code_interpreter as ci

    monkeypatch.setattr(ci.settings, "_jwt_secret_key_generated", True, raising=False)
    assert ci._jwt_secret_is_explicit() is False


def test_explicit_jwt_secret_is_treated_as_stable(monkeypatch) -> None:
    from src.infra.agent.middleware import code_interpreter as ci

    monkeypatch.setattr(ci.settings, "_jwt_secret_key_generated", False, raising=False)
    assert ci._jwt_secret_is_explicit() is True


async def test_routing_appends_ptc_bridge_guidance_when_enabled() -> None:
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(
        sandbox_active=True, ptc_tools=["web_search", "web_fetch"]
    )
    result = await middleware.awrap_model_call(
        _Request(tools=[_EvalTool(), _OtherTool(), _WebFetchTool()]), _handler
    )

    eval_tool = next(t for t in result.tools if t.name == "eval")
    assert "<code_interpreter_ptc>" in eval_tool.description
    assert "tools.webSearch" in eval_tool.description
    assert "tools.webFetch" in eval_tool.description
    # staging 实测（2026-09-19）：模型不知道桥接工具返回 JSON 字符串，
    # 按对象取值失败后花 ~4 分钟/7 次 eval 试错。返回格式提示必须随帧给出。
    assert "JSON.parse" in eval_tool.description
    assert "truncated" in eval_tool.description
    other = next(t for t in result.tools if t.name == "web_search")
    assert "<code_interpreter_ptc>" not in other.description


async def test_routing_omits_ptc_guidance_when_disabled() -> None:
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(sandbox_active=True)
    result = await middleware.awrap_model_call(_Request(), _handler)

    eval_tool = next(t for t in result.tools if t.name == "eval")
    assert "<code_interpreter_ptc>" not in eval_tool.description
    assert "tools.webSearch" not in eval_tool.description


async def test_routing_ptc_guidance_is_idempotent() -> None:
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(sandbox_active=True, ptc_tools=["web_search"])
    first = await middleware.awrap_model_call(_Request(), _handler)
    second = await middleware.awrap_model_call(first, _handler)
    eval_tool = next(t for t in second.tools if t.name == "eval")
    assert eval_tool.description.count("<code_interpreter_ptc>") == 1


class _UnrelatedTool(BaseTool):
    name: str = "image_analyze"
    description: str = "Analyze an image."

    def _run(self, *args, **kwargs):  # pragma: no cover - test stub
        return "ok"


async def test_routing_omits_ptc_guidance_when_bridged_tools_absent() -> None:
    """白名单工具不在当前请求工具集时不宣告 PTC 桥（上游会静默丢弃缺失工具）。"""
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(
        sandbox_active=True, ptc_tools=["web_search", "web_fetch"]
    )
    request = _Request(tools=[_EvalTool(), _UnrelatedTool()])
    result = await middleware.awrap_model_call(request, _handler)

    eval_tool = next(t for t in result.tools if t.name == "eval")
    assert "<code_interpreter_ptc>" not in eval_tool.description
    assert "tools.webSearch" not in eval_tool.description


async def test_routing_filters_ptc_guidance_to_present_tools() -> None:
    """只宣告当前工具集里实际存在的桥，未加载的工具不得出现在指引里。"""
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(
        sandbox_active=True, ptc_tools=["web_search", "web_fetch"]
    )
    result = await middleware.awrap_model_call(_Request(), _handler)

    eval_tool = next(t for t in result.tools if t.name == "eval")
    assert "<code_interpreter_ptc>" in eval_tool.description
    assert "tools.webSearch" in eval_tool.description
    assert "tools.webFetch" not in eval_tool.description


async def test_routing_ptc_guidance_appears_once_tools_become_available() -> None:
    """延迟加载等场景下工具集中途出现：指引帧随之出现，而非构造期定死。"""
    from src.infra.agent.middleware.code_interpreter import CodeInterpreterRoutingMiddleware

    middleware = CodeInterpreterRoutingMiddleware(sandbox_active=True, ptc_tools=["web_search"])
    before = await middleware.awrap_model_call(
        _Request(tools=[_EvalTool(), _UnrelatedTool()]), _handler
    )
    assert (
        "<code_interpreter_ptc>"
        not in next(t for t in before.tools if t.name == "eval").description
    )

    after = await middleware.awrap_model_call(_Request(), _handler)
    assert "tools.webSearch" in next(t for t in after.tools if t.name == "eval").description


async def test_real_ptc_enablement_injects_bridged_tool_reference() -> None:
    """真 quickjs 中间件：PTC 白名单命中 agent 工具集时注入 tools.* API 引用。"""
    from unittest.mock import MagicMock

    from langchain_quickjs import CodeInterpreterMiddleware

    middleware = CodeInterpreterMiddleware(
        subagents=False, ptc=["web_search"], snapshot_signing_key="test-key"
    )
    update = middleware.before_agent(state={}, runtime=MagicMock())
    request = _Request()
    request.state = {"_quickjs_slot_id": update.get("_quickjs_slot_id")}

    result = await middleware.awrap_model_call(request, _handler)

    content = result.system_message.content
    injected = content[-1]["text"] if isinstance(content, list) else str(content)
    assert "### Interpreter" in injected
    assert "tools.webSearch" in injected
    assert "Dispatching Subagents" not in injected
    # PTC 注入只含白名单工具的 API 引用，远小于 JS 子代理编排教程（~9.8k）。
    assert len(injected) < 4000
