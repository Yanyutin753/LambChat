from types import SimpleNamespace

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from src.infra.agent.middleware import (
    PromptCachingMiddleware,
    SectionPromptMiddleware,
    ToolSearchMiddleware,
)
from src.infra.tool.deferred_manager import DEFERRED_TOOL_SEARCH_GUIDE, DeferredToolManager
from src.kernel.config import settings


class _FakeTool(BaseTool):
    name: str
    description: str
    server: str = ""

    def _run(self, *args, **kwargs):
        return "ok"


def test_retag_system_message_prefers_stable_prefix_before_volatile_tail() -> None:
    system_message = SystemMessage(
        content=[
            {"type": "text", "text": "base"},
            {"type": "text", "text": "persona"},
            {"type": "text", "text": "skills"},
            {"type": "text", "text": "memory guide"},
            {"type": "text", "text": "<memory_index>\n- user preference\n</memory_index>"},
            {"type": "text", "text": "## MCP Tools (Deferred)\n\nDynamic tool list follows."},
        ]
    )

    retagged = PromptCachingMiddleware._retag_system_message(
        system_message, {"type": "ephemeral"}, max_cached_blocks=3
    )

    assert isinstance(retagged.content, list)
    assert retagged.content[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in retagged.content[1]
    assert retagged.content[2]["cache_control"] == {"type": "ephemeral"}
    assert retagged.content[3]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in retagged.content[4]
    assert "cache_control" not in retagged.content[5]


def test_retag_system_message_pins_global_base_block_for_cross_context_reuse() -> None:
    system_message = SystemMessage(
        content=[
            {"type": "text", "text": "global base workflow"},
            {"type": "text", "text": "persona for user A"},
            {"type": "text", "text": "skills for session A"},
            {"type": "text", "text": "memory guide"},
        ]
    )

    retagged = PromptCachingMiddleware._retag_system_message(
        system_message, {"type": "ephemeral"}, max_cached_blocks=3
    )

    assert isinstance(retagged.content, list)
    assert retagged.content[0]["cache_control"] == {"type": "ephemeral"}
    tagged_indices = [
        i
        for i, block in enumerate(retagged.content)
        if isinstance(block, dict) and "cache_control" in block
    ]
    assert tagged_indices == [0, 2, 3]


def test_session_stable_runtime_system_sections_are_cacheable() -> None:
    cacheable_blocks = [
        {
            "type": "text",
            "text": "## Sandbox Runtime\n\nCurrent sandbox work_dir: `/tmp/session-a`",
        },
        {"type": "text", "text": "## Sandbox Tools (NOT MCP — DO NOT call directly)"},
        {"type": "text", "text": "## Available Environment Variables"},
        {"type": "text", "text": "## Available Skills\n\n- RedBookSkills"},
        {"type": "text", "text": "## Current Workspace\n\ncwd: /workspace/project"},
    ]

    for block in cacheable_blocks:
        assert not PromptCachingMiddleware._is_volatile_system_block(block)


def test_turn_dynamic_system_sections_are_volatile_for_cache() -> None:
    volatile_blocks = [
        {"type": "text", "text": "<memory_index>\n- preference\n</memory_index>"},
        {"type": "text", "text": "## MCP Tools (Deferred)\n\n- github:create_issue"},
        {"type": "text", "text": "## User Runtime Context\n\nCurrent date: 2026-05-17"},
        {"type": "text", "text": "## Active Goal\nObjective: fix the bug"},
        {
            "type": "text",
            "text": "### Auto Mode (Autonomous Execution)\n\nYou are running in auto mode.",
        },
    ]

    for block in volatile_blocks:
        assert PromptCachingMiddleware._is_volatile_system_block(block)


def test_mcp_tool_search_guide_is_cacheable_while_deferred_list_is_volatile() -> None:
    assert not PromptCachingMiddleware._is_volatile_system_block(
        {"type": "text", "text": "## MCP Tool Search Guide\n\ncall `search_tools` first"}
    )
    assert PromptCachingMiddleware._is_volatile_system_block(
        {"type": "text", "text": "## MCP Tools (Deferred)\n\n- github:create_issue"}
    )


def test_retag_system_message_keeps_session_stable_runtime_sections_in_cache_prefix() -> None:
    system_message = SystemMessage(
        content=[
            {"type": "text", "text": "base"},
            {"type": "text", "text": "persona"},
            {"type": "text", "text": "## Sandbox Runtime\n\nwork_dir: /tmp/session-a"},
            {"type": "text", "text": "## Sandbox Tools (NOT MCP — DO NOT call directly)"},
            {"type": "text", "text": "## Available Environment Variables"},
            {"type": "text", "text": "<memory_index>\n- preference\n</memory_index>"},
        ]
    )

    retagged = PromptCachingMiddleware._retag_system_message(
        system_message, {"type": "ephemeral"}, max_cached_blocks=4
    )

    tagged_indices = [
        i
        for i, block in enumerate(retagged.content)
        if isinstance(block, dict) and "cache_control" in block
    ]

    assert tagged_indices == [0, 2, 3, 4]


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


def test_retag_tools_reorders_volatile_before_stable() -> None:
    """Volatile tools (deferred/discovered) must come before stable tools
    so cache breakpoints always cover the stable tail."""
    tools = [
        _FakeTool(name="read_file", description="stable read tool"),
        _FakeTool(name="write_file", description="stable write tool"),
        _FakeTool(
            name="github:create_issue",
            description="dynamic deferred tool",
            extras={"_lambchat_prompt_cache_volatile": True},
        ),
    ]

    retagged = PromptCachingMiddleware._retag_tools(
        tools, {"type": "ephemeral"}, max_cached_tools=2
    )

    assert retagged is not None
    # Volatile tool first
    assert retagged[0].name == "github:create_issue"
    # Stable tools after, last 2 tagged
    assert retagged[1].name == "read_file"
    assert retagged[1].extras == {"cache_control": {"type": "ephemeral"}}
    assert retagged[2].name == "write_file"
    assert retagged[2].extras == {"cache_control": {"type": "ephemeral"}}


def test_retag_tools_skips_explicitly_volatile_tools() -> None:
    tools = [
        _FakeTool(name="stable_tool", description="stable"),
        _FakeTool(
            name="github:create_issue",
            description="dynamic deferred tool",
            extras={"_lambchat_prompt_cache_volatile": True},
        ),
    ]

    retagged = PromptCachingMiddleware._retag_tools(
        tools, {"type": "ephemeral"}, max_cached_tools=1
    )

    assert retagged is not None
    # Volatile first
    assert retagged[0].name == "github:create_issue"
    # Stable tool tagged
    assert retagged[1].name == "stable_tool"
    assert retagged[1].extras == {"cache_control": {"type": "ephemeral"}}


def test_cacheable_tool_count_ignores_volatile_deferred_tools() -> None:
    tools = [
        _FakeTool(name="stable_tool", description="stable"),
        _FakeTool(
            name="github:create_issue",
            description="dynamic deferred tool",
            extras={"_lambchat_prompt_cache_volatile": True},
        ),
    ]

    assert PromptCachingMiddleware._cacheable_tool_count(tools) == 1


async def test_prompt_caching_middleware_respects_four_breakpoint_budget() -> None:
    middleware = PromptCachingMiddleware()

    class _AnthropicLike:
        pass

    _AnthropicLike.__module__ = "langchain_anthropic.chat_models"

    class _Request:
        def __init__(self) -> None:
            self.model = _AnthropicLike()
            self.system_message = SystemMessage(
                content=[
                    {"type": "text", "text": "base"},
                    {"type": "text", "text": "persona"},
                    {"type": "text", "text": "skills"},
                    {"type": "text", "text": "memory"},
                    {"type": "text", "text": "## MCP Tools (Deferred)\n\nDynamic deferred list."},
                ]
            )
            self.tools = [_FakeTool(name=f"tool_{i}", description=f"tool {i}") for i in range(5)]

        def override(self, **kwargs):
            clone = _Request()
            clone.model = kwargs.get("model", self.model)
            clone.system_message = kwargs.get("system_message", self.system_message)
            clone.tools = kwargs.get("tools", self.tools)
            return clone

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)

    system_breakpoints = sum(
        1
        for block in result.system_message.content
        if isinstance(block, dict) and "cache_control" in block
    )
    tool_breakpoints = sum(
        1
        for tool in result.tools
        if getattr(tool, "extras", None) and "cache_control" in tool.extras
    )

    assert system_breakpoints + tool_breakpoints == 4
    assert result.system_message.content[0]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in result.system_message.content[1]
    assert result.system_message.content[2]["cache_control"] == {"type": "ephemeral"}
    assert result.system_message.content[3]["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in result.system_message.content[4]
    assert result.tools[-1].extras == {"cache_control": {"type": "ephemeral"}}


async def test_prompt_caching_preserves_stable_search_guide_and_tool_after_discovery() -> None:
    middleware = PromptCachingMiddleware()

    class _AnthropicLike:
        pass

    _AnthropicLike.__module__ = "langchain_anthropic.chat_models"

    class _Request:
        def __init__(self) -> None:
            self.model = _AnthropicLike()
            self.system_message = SystemMessage(
                content=[
                    {"type": "text", "text": "base"},
                    {"type": "text", "text": "persona"},
                    {"type": "text", "text": "skills"},
                    {
                        "type": "text",
                        "text": "## MCP Tool Search Guide\n\ncall `search_tools` first",
                    },
                    {
                        "type": "text",
                        "text": "## MCP Tools (Deferred)\n\n- beta:list: beta list",
                    },
                ]
            )
            self.tools = [
                _FakeTool(name="read_file", description="stable read tool"),
                _FakeTool(name="search_tools", description="stable search tool"),
                _FakeTool(name="alpha:create", description="discovered schema"),
            ]

        def override(self, **kwargs):
            clone = _Request()
            clone.model = kwargs.get("model", self.model)
            clone.system_message = kwargs.get("system_message", self.system_message)
            clone.tools = kwargs.get("tools", self.tools)
            return clone

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)

    tagged_system_indices = [
        i
        for i, block in enumerate(result.system_message.content)
        if isinstance(block, dict) and "cache_control" in block
    ]
    assert tagged_system_indices == [0, 2, 3]
    assert result.tools[1].name == "search_tools"
    assert result.tools[2].name == "alpha:create"
    assert result.tools[2].extras == {"cache_control": {"type": "ephemeral"}}


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


async def test_prompt_caching_middleware_skips_minimax_anthropic_passive_cache() -> None:
    middleware = PromptCachingMiddleware()

    class _MiniMaxAnthropicLike:
        model = "MiniMax-M2.7"
        anthropic_api_url = "https://api.minimaxi.com/anthropic"

    _MiniMaxAnthropicLike.__module__ = "langchain_anthropic.chat_models"

    class _Request:
        def __init__(self) -> None:
            self.model = _MiniMaxAnthropicLike()
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


def test_prompt_caching_middleware_uses_settings_for_cache_limits(monkeypatch) -> None:
    monkeypatch.setattr(settings, "PROMPT_CACHE_MAX_SYSTEM_BLOCKS", 6, raising=False)
    monkeypatch.setattr(settings, "PROMPT_CACHE_MAX_TOOLS", 5, raising=False)

    middleware = PromptCachingMiddleware()

    assert middleware._max_cached_system_blocks == 6
    assert middleware._max_cached_tools == 5


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


def test_deferred_manager_fork_does_not_mutate_parent_discoveries() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
        pre_discovered_names=["alpha:create"],
    )

    forked = manager.fork_for_scope("subagent")
    forked.discover_tools(["beta:list"])

    assert manager.discovered_names == ["alpha:create"]
    assert forked.discovered_names == ["alpha:create", "beta:list"]


def test_deferred_manager_fork_inherits_parent_later_discoveries() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
        pre_discovered_names=["alpha:create"],
    )
    forked = manager.fork_for_scope("subagent")

    manager.discover_tools(["beta:list"])

    assert forked.discovered_names == ["alpha:create", "beta:list"]
    assert [tool.name for tool in forked.get_discovered_tools()] == ["alpha:create", "beta:list"]


async def test_tool_search_middleware_intercepts_registered_search_tool_with_own_manager() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
        pre_discovered_names=["alpha:create"],
    )
    middleware = ToolSearchMiddleware(deferred_manager=manager, search_limit=5)
    request = SimpleNamespace(
        tool_call={
            "name": "search_tools",
            "args": {"query": "select:beta:list"},
            "id": "call-1",
        },
        tool=object(),
    )

    async def _handler(_request):
        return ToolMessage(content="wrong manager", tool_call_id="call-1", name="search_tools")

    result = await middleware.awrap_tool_call(request, _handler)

    assert isinstance(result, ToolMessage)
    assert "beta:list" in result.content
    assert manager.discovered_names == ["alpha:create", "beta:list"]


async def test_tool_search_middleware_injects_discovered_tools_as_cacheable() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
        ],
        session_id="session-1",
        pre_discovered_names=["alpha:create"],
    )
    middleware = ToolSearchMiddleware(deferred_manager=manager, search_limit=5)

    class _Request:
        def __init__(self) -> None:
            self.system_message = SystemMessage(content=[{"type": "text", "text": "base"}])
            self.tools = []

        def override(self, **kwargs):
            clone = _Request()
            clone.system_message = kwargs.get("system_message", self.system_message)
            clone.tools = kwargs.get("tools", self.tools)
            return clone

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)
    discovered_tool = next(tool for tool in result.tools if tool.name == "alpha:create")

    assert "_lambchat_prompt_cache_volatile" not in (discovered_tool.extras or {})


async def test_tool_search_middleware_skips_duplicate_search_guide_when_already_present() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
        ],
        session_id="session-1",
    )
    middleware = ToolSearchMiddleware(deferred_manager=manager, search_limit=5)

    class _Request:
        def __init__(self) -> None:
            self.system_message = SystemMessage(
                content=[
                    {"type": "text", "text": "base"},
                    {"type": "text", "text": DEFERRED_TOOL_SEARCH_GUIDE},
                ]
            )
            self.tools = []

        def override(self, **kwargs):
            clone = _Request()
            clone.system_message = kwargs.get("system_message", self.system_message)
            clone.tools = kwargs.get("tools", self.tools)
            return clone

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)
    system_text = "\n".join(
        block["text"] for block in result.system_message.content if block.get("type") == "text"
    )

    assert system_text.count("## Tool Search Guide") == 1
    assert "## MCP Tools (Deferred)" in system_text


def test_deferred_prompt_does_not_repeat_loaded_tool_names() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
        pre_discovered_names=["alpha:create"],
    )

    prompt = manager.get_deferred_stubs_string()

    assert "## MCP Tools (Loaded)" not in prompt
    assert "- alpha:create" not in prompt
    assert "- beta:list" in prompt
    assert "beta list" not in prompt


def test_deferred_prompt_blocks_split_stable_rules_and_dynamic_tool_list() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
    )

    blocks = manager.get_deferred_prompt_blocks()

    assert len(blocks) == 2
    assert blocks[0].startswith("## Tool Search Guide")
    assert "search_tools" in blocks[0]
    assert blocks[1].startswith("## MCP Tools (Deferred)")
    assert "- beta:list" in blocks[1]
    assert "beta list" not in blocks[1]


def test_deferred_prompt_keeps_search_guide_stable_after_discovery() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
    )

    before = manager.get_deferred_prompt_blocks()
    manager.discover_tools(["alpha:create"])
    after = manager.get_deferred_prompt_blocks()

    assert before[0] == after[0]
    assert "- alpha:create" in before[1]
    assert "- alpha:create" not in after[1]
    assert "- beta:list" in after[1]


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

    assert prompt.index("- alpha:create") < prompt.index("- zeta:lookup")


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
    assert "- alpha:create" in prompt
    assert "alpha create" not in prompt


def test_deferred_prompt_lists_every_mcp_name_without_descriptions() -> None:
    tools = [
        _FakeTool(
            name=f"server:{index:03d}",
            description=f"private description {index}",
            server="server",
        )
        for index in range(101)
    ]
    manager = DeferredToolManager(
        all_deferred_tools=tools,
        session_id="session-1",
    )

    prompt = manager.get_deferred_stubs_string()

    assert {line.removeprefix("- ") for line in prompt.splitlines() if line.startswith("- ")} == {
        tool.name for tool in tools
    }
    assert all(tool.description not in prompt for tool in tools)
    assert "not shown" not in prompt


def test_deferred_prompt_splits_mcp_names_and_system_descriptions() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="github:create", description="Create a GitHub issue", server="github")
        ],
        deferred_system_tools=[
            _FakeTool(
                name="image_generate",
                description="生成图片\nLong details must not be included",
                server="lambchat_internal",
            )
        ],
        session_id="session-1",
    )

    prompt = manager.get_deferred_stubs_string()

    assert "## MCP Tools (Deferred)\n\n- github:create" in prompt
    assert "Create a GitHub issue" not in prompt
    assert "## System Tools (Deferred)\n\n- image_generate: 生成图片" in prompt
    assert "Long details" not in prompt


def test_deferred_manager_prefers_system_tool_on_duplicate_name(caplog) -> None:
    mcp = _FakeTool(name="shared", description="MCP version", server="remote")
    system = _FakeTool(name="shared", description="System version", server="lambchat_internal")

    manager = DeferredToolManager(
        all_deferred_tools=[mcp],
        deferred_system_tools=[system],
        session_id="session-1",
    )

    assert manager.get_tool("shared") is system
    assert "duplicate" in caplog.text.lower()


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
