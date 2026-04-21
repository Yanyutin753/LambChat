from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool

from src.infra.agent.middleware import PromptCachingMiddleware, SectionPromptMiddleware
from src.infra.tool.deferred_manager import DeferredToolManager


class _FakeTool(BaseTool):
    name: str
    description: str
    server: str = ""

    def _run(self, *args, **kwargs):
        return "ok"


def test_retag_system_message_tags_multiple_tail_blocks() -> None:
    system_message = SystemMessage(
        content=[
            {"type": "text", "text": "base"},
            {"type": "text", "text": "stable"},
            {"type": "text", "text": "memory"},
            {"type": "text", "text": "dynamic"},
        ]
    )

    retagged = PromptCachingMiddleware._retag_system_message(
        system_message, {"type": "ephemeral"}, max_cached_blocks=3
    )

    assert isinstance(retagged.content, list)
    assert "cache_control" not in retagged.content[0]
    assert retagged.content[1]["cache_control"] == {"type": "ephemeral"}
    assert retagged.content[2]["cache_control"] == {"type": "ephemeral"}
    assert retagged.content[3]["cache_control"] == {"type": "ephemeral"}


def test_retag_tools_tags_multiple_tail_tools() -> None:
    tools = [
        _FakeTool(name="alpha", description="a"),
        _FakeTool(name="beta", description="b"),
        _FakeTool(name="gamma", description="c"),
    ]

    retagged = PromptCachingMiddleware._retag_tools(
        tools, {"type": "ephemeral"}, max_cached_tools=2
    )

    assert retagged is not None
    assert retagged[0].extras in (None, {})
    assert retagged[1].extras == {"cache_control": {"type": "ephemeral"}}
    assert retagged[2].extras == {"cache_control": {"type": "ephemeral"}}


async def test_prompt_caching_middleware_skips_non_anthropic_models() -> None:
    middleware = PromptCachingMiddleware()

    class _Request:
        def __init__(self) -> None:
            self.model = object()
            self.system_message = SystemMessage(content=[{"type": "text", "text": "base"}])
            self.tools = [_FakeTool(name="alpha", description="a")]

        def override(self, **kwargs):
            clone = _Request()
            clone.model = kwargs.get("model", self.model)
            clone.system_message = kwargs.get("system_message", self.system_message)
            clone.tools = kwargs.get("tools", self.tools)
            return clone

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)

    assert isinstance(result.system_message.content, list)
    assert "cache_control" not in result.system_message.content[0]
    assert result.tools[0].extras in (None, {})


async def test_prompt_caching_middleware_tags_anthropic_wrapped_models() -> None:
    middleware = PromptCachingMiddleware()

    class _AnthropicLike:
        pass

    _AnthropicLike.__module__ = "langchain_anthropic.chat_models"

    class _Binding:
        def __init__(self) -> None:
            self.bound = _AnthropicLike()

    class _Request:
        def __init__(self) -> None:
            self.model = _Binding()
            self.system_message = SystemMessage(content=[{"type": "text", "text": "base"}])
            self.tools = [_FakeTool(name="alpha", description="a")]

        def override(self, **kwargs):
            clone = _Request()
            clone.model = kwargs.get("model", self.model)
            clone.system_message = kwargs.get("system_message", self.system_message)
            clone.tools = kwargs.get("tools", self.tools)
            return clone

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)

    assert isinstance(result.system_message.content, list)
    assert result.system_message.content[0]["cache_control"] == {"type": "ephemeral"}
    assert result.tools[0].extras == {"cache_control": {"type": "ephemeral"}}


def test_deferred_manager_returns_discovered_tools_in_sorted_order() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="zeta:lookup", description="zeta lookup", server="zeta"),
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
        pre_discovered_names=["zeta:lookup", "alpha:create"],
    )

    discovered = manager.get_discovered_tools()

    assert [tool.name for tool in discovered] == ["alpha:create", "zeta:lookup"]


def test_deferred_prompt_string_is_stably_sorted() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="zeta:lookup", description="zeta lookup", server="zeta"),
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
        pre_discovered_names=["beta:list"],
    )

    prompt = manager.get_deferred_stubs_string()

    assert prompt.index("- beta:list") < prompt.index("- alpha:create: alpha create")
    assert prompt.index("- alpha:create: alpha create") < prompt.index("- zeta:lookup: zeta lookup")


def test_deferred_prompt_string_survives_prior_stub_cache_access() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
        ],
        session_id="session-1",
    )

    stubs = manager.get_deferred_stubs()
    prompt = manager.get_deferred_stubs_string()

    assert [stub.name for stub in stubs] == ["alpha:create"]
    assert "## MCP Tools (Deferred)" in prompt
    assert "- alpha:create: alpha create" in prompt


async def test_section_prompt_middleware_appends_separate_blocks() -> None:
    middleware = SectionPromptMiddleware(sections=["skills block", "memory block"])

    class _Request:
        def __init__(self) -> None:
            self.system_message = SystemMessage(content=[{"type": "text", "text": "base"}])

        def override(self, **kwargs):
            clone = _Request()
            clone.system_message = kwargs.get("system_message", self.system_message)
            return clone

    async def _handler(request):
        return request.system_message

    result = await middleware.awrap_model_call(_Request(), _handler)

    assert isinstance(result.content, list)
    assert [block["text"] for block in result.content] == ["base", "skills block", "memory block"]
