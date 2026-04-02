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
    assert prompt.index("- alpha:create: alpha create") < prompt.index(
        "- zeta:lookup: zeta lookup"
    )


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
