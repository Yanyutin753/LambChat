from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool


class _MemoryRecallTool(BaseTool):
    """Minimal stand-in for the real memory_recall tool."""

    name: str = "memory_recall"
    description: str = "base memory recall description"

    def _run(self, query: str) -> str:  # pragma: no cover - unused in tests
        return query


from src.infra.agent.middleware import (
    MemoryIndexMiddleware,
    SectionPromptMiddleware,
    ToolSearchMiddleware,
)
from src.infra.tool.deferred_manager import DEFERRED_TOOL_SEARCH_GUIDE, DeferredToolManager


class _FakeTool(BaseTool):
    name: str
    description: str
    server: str = ""

    def _run(self, *args, **kwargs):
        return "ok"


def test_deferred_manager_returns_discovered_tools_in_discovery_order() -> None:
    """Order follows discovery (or persisted restore) order, not name order.

    The tools list is part of the provider prompt-cache prefix; the online
    path appends newly discovered tools in discovery order, so the restore
    path must reproduce the same order to avoid a full-prefix cache miss
    after a process restart.
    """
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

    assert [tool.name for tool in discovered] == ["zeta:lookup", "alpha:create"]


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


def test_deferred_manager_fork_rebuilds_prompt_after_parent_discovery() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
    )
    forked = manager.fork_for_scope("subagent")

    before = forked.get_deferred_stubs_string()
    manager.discover_tools(["alpha:create"])
    after = forked.get_deferred_stubs_string()

    # The stub list is frozen at session scope: discovery must never rewrite
    # the search_tools description, or the provider prompt-cache prefix
    # breaks exactly at the search_tools position.
    assert before == after
    assert "- alpha:create" in after
    assert "- beta:list" in after


def test_deferred_stubs_string_is_frozen_across_discovery() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
    )

    before = manager.get_deferred_stubs_string()
    manager.discover_tools(["alpha:create"])
    after = manager.get_deferred_stubs_string()

    assert before == after


def test_deferred_stubs_string_is_identical_for_fork_and_parent() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
    )
    manager.discover_tools(["alpha:create"])
    forked = manager.fork_for_scope("subagent")

    # Main and sub agents alternate requests against the same cache prefix;
    # their stub lists must be byte-identical regardless of discovery state.
    assert forked.get_deferred_stubs_string() == manager.get_deferred_stubs_string()


def test_deferred_stubs_string_ignores_pre_discovered_restore_state() -> None:
    fresh = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
        ],
        session_id="session-1",
    )
    restored = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
        ],
        session_id="session-1",
        pre_discovered_names=["alpha:create"],
    )

    assert restored.get_deferred_stubs_string() == fresh.get_deferred_stubs_string()


async def test_search_tools_description_is_stable_across_model_calls() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
    )
    middleware = ToolSearchMiddleware(deferred_manager=manager, search_limit=5)

    class _Request:
        def __init__(self) -> None:
            self.system_message = SystemMessage(content="base")
            self.tools = []

        def override(self, **kwargs):
            clone = _Request()
            clone.tools = kwargs.get("tools", self.tools)
            return clone

    async def _handler(request):
        return request

    first = await middleware.awrap_model_call(_Request(), _handler)
    first_desc = next(t for t in first.tools if t.name == "search_tools").description

    manager.discover_tools(["alpha:create"])
    second = await middleware.awrap_model_call(_Request(), _handler)
    second_desc = next(t for t in second.tools if t.name == "search_tools").description

    assert first_desc == second_desc


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


async def test_tool_search_middleware_preserves_discovered_tool_extras() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(
                name="alpha:create",
                description="alpha create",
                server="alpha",
                extras={"existing": "value"},
            ),
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

    assert discovered_tool is manager.get_tool("alpha:create")
    assert discovered_tool.extras == {"existing": "value"}


async def test_tool_search_middleware_keeps_manager_order_then_appends_search() -> None:
    zeta = _FakeTool(name="zeta:lookup", description="zeta lookup", server="zeta")
    alpha = _FakeTool(name="alpha:create", description="alpha create", server="alpha")
    manager = DeferredToolManager(
        all_deferred_tools=[zeta, alpha],
        session_id="session-1",
        pre_discovered_names=[zeta.name, alpha.name],
    )
    manager.get_discovered_tools = lambda: [zeta, alpha]  # type: ignore[method-assign]
    middleware = ToolSearchMiddleware(deferred_manager=manager, search_limit=5)
    existing = _FakeTool(name="existing", description="existing")

    class _Request:
        def __init__(self) -> None:
            self.system_message = SystemMessage(content=[{"type": "text", "text": "base"}])
            self.tools = [existing]

        def override(self, **kwargs):
            clone = _Request()
            clone.system_message = kwargs.get("system_message", self.system_message)
            clone.tools = kwargs.get("tools", self.tools)
            return clone

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)

    assert result.tools[:3] == [existing, zeta, alpha]
    assert [tool.name for tool in result.tools] == [
        "existing",
        "zeta:lookup",
        "alpha:create",
        "search_tools",
    ]


async def test_tool_search_middleware_does_not_duplicate_existing_search_tool() -> None:
    discovered = _FakeTool(name="zeta:lookup", description="zeta lookup", server="zeta")
    manager = DeferredToolManager(
        all_deferred_tools=[discovered],
        session_id="session-1",
        pre_discovered_names=[discovered.name],
    )
    middleware = ToolSearchMiddleware(deferred_manager=manager, search_limit=5)
    search_tool = middleware._get_search_tool()
    existing = _FakeTool(name="existing", description="existing")

    class _Request:
        def __init__(self) -> None:
            self.system_message = SystemMessage(content=[{"type": "text", "text": "base"}])
            self.tools = [existing, search_tool]

        def override(self, **kwargs):
            clone = _Request()
            clone.system_message = kwargs.get("system_message", self.system_message)
            clone.tools = kwargs.get("tools", self.tools)
            return clone

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)

    # The search_tools entry is replaced by an enriched copy (frozen stubs now
    # include already-discovered names), but it must never be duplicated.
    assert [tool.name for tool in result.tools] == [
        "existing",
        "search_tools",
        "zeta:lookup",
    ]


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

    # Codex-style layering: deferred-tool metadata goes into the search_tools
    # description; the system prompt is never modified by this middleware.
    assert result.system_message.content == [
        {"type": "text", "text": "base"},
        {"type": "text", "text": DEFERRED_TOOL_SEARCH_GUIDE},
    ]
    search_tool = next(t for t in result.tools if t.name == "search_tools")
    description = search_tool.description
    assert description.count("## Tool Search Guide") == 1
    assert "## MCP Tools (Deferred)" in description
    assert "<deferred_tools>" in description


def test_deferred_search_guide_has_compact_budget() -> None:
    assert len(DEFERRED_TOOL_SEARCH_GUIDE) <= 300


def test_deferred_prompt_keeps_loaded_tool_names_as_search_hints() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
        pre_discovered_names=["alpha:create"],
    )

    prompt = manager.get_deferred_stubs_string()

    # Frozen stub list: names remain as searchable hints even after loading;
    # descriptions stay hidden and no "(Loaded)" section is introduced.
    assert "## MCP Tools (Loaded)" not in prompt
    assert "- alpha:create" in prompt
    assert "- beta:list" in prompt
    assert "beta list" not in prompt


def test_deferred_prompt_string_contains_complete_guide_and_tool_list() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
    )

    prompt = manager.get_deferred_stubs_string()

    assert prompt.startswith("## Tool Search Guide")
    assert "search_tools" in prompt
    assert "## MCP Tools (Deferred)" in prompt
    assert "- beta:list" in prompt
    assert "beta list" not in prompt


def test_deferred_prompt_string_is_unchanged_after_discovery() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="alpha:create", description="alpha create", server="alpha"),
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
    )

    before = manager.get_deferred_stubs_string()
    manager.discover_tools(["alpha:create"])
    after = manager.get_deferred_stubs_string()

    assert before.startswith("## Tool Search Guide")
    assert before == after


async def test_tool_search_middleware_appends_one_complete_deferred_prompt_block() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(name="beta:list", description="beta list", server="beta"),
        ],
        session_id="session-1",
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

    # The complete deferred prompt (guide + stubs) lands on the search_tools
    # description as one framed block; the system prompt stays untouched.
    assert result.system_message.content == [{"type": "text", "text": "base"}]
    search_tool = next(t for t in result.tools if t.name == "search_tools")
    assert (
        "<deferred_tools>" in search_tool.description
        and "## MCP Tools (Deferred)\n\n- beta:list" in search_tool.description
    )


async def test_tool_search_middleware_puts_env_keys_under_deferred_env_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import env_var_prompt

    async def fake_build_env_var_prompt(user_id: str) -> str:
        assert user_id == "user-1"
        return "## Available Environment Variables\n\n- `FIRECRAWL_API_KEY`"

    monkeypatch.setattr(env_var_prompt, "build_env_var_prompt", fake_build_env_var_prompt)
    manager = DeferredToolManager(
        all_deferred_tools=[],
        deferred_system_tools=[
            _FakeTool(
                name="env_var_list",
                description="List the current user's saved environment variable keys.",
            ),
            _FakeTool(name="env_var_set", description="Set an environment variable."),
        ],
        session_id="session-1",
    )
    middleware = ToolSearchMiddleware(
        deferred_manager=manager,
        search_limit=5,
        user_id="user-1",
    )

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
    search_tool = next(tool for tool in result.tools if tool.name == "search_tools")

    assert "## System Tools (Deferred)" in search_tool.description
    assert "- env_var_list: List the current user's saved environment variable keys." in search_tool.description
    assert "## Available Environment Variables" in search_tool.description
    assert "- `FIRECRAWL_API_KEY`" in search_tool.description
    assert result.system_message.content == [{"type": "text", "text": "base"}]


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


async def test_section_prompt_middleware_appends_one_normalized_block() -> None:
    middleware = SectionPromptMiddleware(sections=[" skills block  ", "memory block"])

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
    assert [block["text"] for block in result.content] == [
        "base",
        "skills block\n\nmemory block",
    ]


async def test_memory_index_keeps_current_user_question_as_final_message(monkeypatch) -> None:
    middleware = MemoryIndexMiddleware(user_id="user-1")
    history = HumanMessage(content="earlier question")
    current = HumanMessage(content="current question")

    async def _build_index(_user_id: str, *, session_id=None) -> str:
        return "<memory_index>\n- preference\n</memory_index>"

    monkeypatch.setattr(
        "src.infra.agent.middleware.prompt_injection._build_memory_index_for_user",
        _build_index,
    )

    class _Request:
        def __init__(self, messages=None, system_message=None, tools=None) -> None:
            self.messages = messages or [history, current]
            self.system_message = system_message or SystemMessage(content="base")
            self.tools = tools if tools is not None else [_MemoryRecallTool()]

        def override(self, **kwargs):
            return _Request(
                kwargs.get("messages", self.messages),
                kwargs.get("system_message", self.system_message),
                kwargs.get("tools", self.tools),
            )

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)

    # Codex-style layering: the memory index is a framed block appended to
    # the memory_recall tool description (versioned by content); messages and
    # the system prompt are left completely untouched.
    assert result.messages[0] is history
    assert result.messages[1] is current
    assert len(result.messages) == 2
    assert current.content == "current question"
    assert result.system_message.content == "base"
    recall = next(t for t in result.tools if t.name == "memory_recall")
    assert "base memory recall description" in recall.description
    assert "<memory_index_context>" in recall.description
    assert "Not authored by the user" in recall.description
    assert "<memory_index>" in recall.description


async def test_memory_index_stays_before_current_user_during_tool_loop(monkeypatch) -> None:
    middleware = MemoryIndexMiddleware(user_id="user-1")
    previous = HumanMessage(content="previous question")
    current = HumanMessage(content="current question")
    assistant = AIMessage(
        content="",
        tool_calls=[{"name": "lookup", "args": {}, "id": "call-1"}],
    )
    tool = ToolMessage(content="result", tool_call_id="call-1")

    async def _build_index(_user_id: str, *, session_id=None) -> str:
        return "<memory_index>\n- preference\n</memory_index>"

    monkeypatch.setattr(
        "src.infra.agent.middleware.prompt_injection._build_memory_index_for_user",
        _build_index,
    )

    class _Request:
        def __init__(self, messages=None, system_message=None, tools=None) -> None:
            self.messages = messages or [previous, current, assistant, tool]
            self.system_message = system_message or SystemMessage(content="base")
            self.tools = tools if tools is not None else [_MemoryRecallTool()]

        def override(self, **kwargs):
            return _Request(
                kwargs.get("messages", self.messages),
                kwargs.get("system_message", self.system_message),
                kwargs.get("tools", self.tools),
            )

    async def _handler(request):
        return request

    result = await middleware.awrap_model_call(_Request(), _handler)

    # The message sequence and system prompt are never modified; the index
    # rides on the memory_recall tool description instead.
    assert result.messages == [previous, current, assistant, tool]
    assert current.content == "current question"
    assert result.system_message.content == "base"
    recall = next(t for t in result.tools if t.name == "memory_recall")
    assert "<memory_index_context>" in recall.description


def test_main_agents_assemble_goal_and_auto_mode_as_ordinary_prompt_sections() -> None:
    from inspect import getsource

    from src.agents.fast_agent.nodes import fast_agent_node
    from src.agents.search_agent.nodes import agent_node
    from src.agents.team_agent.nodes import team_router_node
    from src.api.routes.chat import append_turn_context_prompt as _chat_import  # noqa: F401

    chat_source = getsource(_load_module("src.api.routes.chat"))
    # Goal/auto-mode context is persisted into the user message at write time
    # (same layering as the timestamp and skills prompt), keeping the sent
    # prompt byte-identical to the stored history.
    assert "append_turn_context_prompt(" in chat_source
    assert "request.auto_mode" in chat_source

    for node in (fast_agent_node, agent_node, team_router_node):
        source = getsource(node)
        # Agents must NOT inject per-turn goal/auto content at request time:
        # request-time injection forks the prompt prefix between turns and
        # defeats provider prompt caching.
        assert "build_goal_prompt_section" not in source
        assert "AUTO_MODE_PROMPT_SECTION" not in source
        assert "TurnContextPromptMiddleware" not in source
        assert "VolatileSectionPromptMiddleware" not in source


def _load_module(dotted: str):
    import importlib

    return importlib.import_module(dotted)


@pytest.mark.asyncio
async def test_memory_index_snapshotted_per_user_with_ttl(monkeypatch) -> None:
    """With a session_id the index is built once and reused (Codex-style
    session snapshot), so auto memory capture cannot churn the tools prefix
    every turn."""
    from src.infra.agent.middleware import prompt_injection

    prompt_injection._MEMORY_INDEX_SNAPSHOTS.clear()
    calls = {"n": 0}

    async def _uncached(_user_id: str) -> str:
        calls["n"] += 1
        return "<memory_index>\n- item\n</memory_index>"

    monkeypatch.setattr(prompt_injection, "_build_memory_index_uncached", _uncached)

    first = await prompt_injection._build_memory_index_for_user("u1", session_id="s1")
    second = await prompt_injection._build_memory_index_for_user("u1", session_id="s1")
    assert first == second == "<memory_index>\n- item\n</memory_index>"
    assert calls["n"] == 1

    # Without a session_id (legacy call sites) every call rebuilds.
    await prompt_injection._build_memory_index_for_user("u1")
    assert calls["n"] == 2

    prompt_injection._MEMORY_INDEX_SNAPSHOTS.clear()
