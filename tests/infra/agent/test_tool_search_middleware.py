from types import SimpleNamespace

from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool

from src.infra.agent import middleware as middleware_package
from src.infra.agent.middleware import SectionPromptMiddleware, ToolSearchMiddleware
from src.infra.tool.deferred_manager import DEFERRED_TOOL_SEARCH_GUIDE, DeferredToolManager


class _FakeTool(BaseTool):
    name: str
    description: str
    server: str = ""

    def _run(self, *args, **kwargs):
        return "ok"


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

    assert discovered_tool.extras == {"existing": "value"}


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


def test_deferred_search_guide_has_compact_budget() -> None:
    assert len(DEFERRED_TOOL_SEARCH_GUIDE) <= 300


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


async def test_volatile_sections_append_after_session_stable_sections() -> None:
    middleware_type = getattr(middleware_package, "VolatileSectionPromptMiddleware", None)
    assert middleware_type is not None

    middleware = middleware_type(
        sections=[
            "## Active Goal\nObjective: ship",
            "### Auto Mode (Autonomous Execution)",
        ]
    )

    class _Request:
        def __init__(self) -> None:
            self.system_message = SystemMessage(
                content=[
                    {"type": "text", "text": "base"},
                    {"type": "text", "text": "## Sandbox Runtime\nwork_dir: /workspace"},
                    {"type": "text", "text": "## Available Environment Variables\n- TOKEN"},
                ]
            )

        def override(self, **kwargs):
            clone = _Request()
            clone.system_message = kwargs.get("system_message", self.system_message)
            return clone

    async def _handler(request):
        return request.system_message

    result = await middleware.awrap_model_call(_Request(), _handler)

    assert [block["text"].splitlines()[0] for block in result.content] == [
        "base",
        "## Sandbox Runtime",
        "## Available Environment Variables",
        "## Active Goal",
        "### Auto Mode (Autonomous Execution)",
    ]
