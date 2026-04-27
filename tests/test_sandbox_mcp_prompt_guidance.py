import importlib.util
from pathlib import Path

import pytest

from src.infra.tool.deferred_manager import DeferredToolManager
from src.infra.tool.sandbox_mcp_prompt import (
    _MAX_TOOLS_IN_PROMPT,
    _fetch_and_format,
    _format_tools_list,
    _format_tools_list_sections,
    _maybe_append_overflow_hint,
)
from src.infra.tool.tool_search_tool import ToolSearchTool


def _load_module_from_path(module_name: str, relative_path: str):
    path = Path(__file__).parents[1] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class _FakeTool:
    def __init__(self, name: str, description: str, server: str = "") -> None:
        self.name = name
        self.description = description
        self.server = server


class _FakeManager:
    pass


class _SearchArgsSchema(_FakeManager):
    @classmethod
    def model_json_schema(cls):
        return {
            "type": "object",
            "properties": {"title": {"type": "string"}},
            "required": ["title"],
        }


def test_deferred_prompt_excludes_sandbox_mcp_from_search_tools() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(
                name="github:create_issue",
                description="Create an issue in GitHub.",
                server="github",
            )
        ],
        session_id="session-1",
    )

    prompt = manager.get_deferred_stubs_string()

    assert "search_tools" in prompt
    assert "does NOT search sandbox tools" in prompt
    assert "use `execute` with `mcporter`" in prompt


def test_deferred_prompt_tells_model_to_search_before_using_tool() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool(
                name="github:create_issue",
                description="Create an issue in GitHub.",
                server="github",
            )
        ],
        session_id="session-1",
    )

    prompt = manager.get_deferred_stubs_string()

    assert "If one of these tools would help" in prompt
    assert "call `search_tools` first" in prompt
    assert "then use that tool normally" in prompt


def test_search_tools_description_uses_server_tool_exact_name_format() -> None:
    description = ToolSearchTool(manager=_FakeManager()).description

    assert "select:github:create_issue" in description
    assert "select:mcp__github__create_issue" not in description
    assert "Use exact tool names as shown" in description


async def test_search_tools_result_tells_model_to_call_loaded_tool_next() -> None:
    tool = _FakeTool("github:create_issue", "Create issue", server="github")
    tool.args_schema = _SearchArgsSchema
    manager = DeferredToolManager(all_deferred_tools=[tool], session_id="session-1")
    search_tool = ToolSearchTool(manager=manager, search_limit=5)

    result = await search_tool._arun("select:github:create_issue")

    assert "call it directly next" in result
    assert "github:create_issue" in result


def test_sandbox_mcp_prompt_tells_model_to_use_mcporter_not_search_tools() -> None:
    prompt, total = _format_tools_list(
        {
            "servers": [
                {
                    "name": "playwright",
                    "status": "ok",
                    "tools": [
                        {
                            "name": "screenshot",
                            "description": "Take a screenshot.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"url": {"type": "string"}},
                                "required": ["url"],
                            },
                        }
                    ],
                }
            ]
        }
    )

    assert total == 1
    assert "NOT MCP" in prompt
    assert "execute" in prompt
    assert "mcporter call" in prompt


def test_sandbox_mcp_prompt_sections_split_intro_and_tool_listing() -> None:
    sections, total = _format_tools_list_sections(
        {
            "servers": [
                {
                    "name": "playwright",
                    "status": "ok",
                    "tools": [
                        {
                            "name": "screenshot",
                            "description": "Take a screenshot.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"url": {"type": "string"}},
                                "required": ["url"],
                            },
                        }
                    ],
                }
            ]
        }
    )

    assert total == 1
    assert len(sections) == 2
    assert "Sandbox Tools" in sections[0]
    assert "`playwright.screenshot`" in sections[1]


def test_sandbox_overflow_hint_mentions_schema_inspection() -> None:
    prompt = _maybe_append_overflow_hint("sandbox prompt\n", _MAX_TOOLS_IN_PROMPT + 1)

    assert "mcporter list" in prompt
    assert "mcporter list --schema" in prompt


def test_sandbox_mcp_prompt_requires_schema_inspection_before_first_call() -> None:
    prompt, total = _format_tools_list(
        {
            "servers": [
                {
                    "name": "playwright",
                    "status": "ok",
                    "tools": [
                        {
                            "name": "screenshot",
                            "description": "Take a screenshot.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"url": {"type": "string"}},
                                "required": ["url"],
                            },
                        }
                    ],
                }
            ]
        }
    )

    assert total == 1
    assert "before the first `mcporter call`" in prompt
    assert "must inspect its parameters via `execute`" in prompt
    assert "`mcporter list --schema`" in prompt


def test_sandbox_mcp_prompt_discourages_repo_wide_grep_searches() -> None:
    prompt, total = _format_tools_list(
        {
            "servers": [
                {
                    "name": "playwright",
                    "status": "ok",
                    "tools": [
                        {
                            "name": "screenshot",
                            "description": "Take a screenshot.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"url": {"type": "string"}},
                                "required": ["url"],
                            },
                        }
                    ],
                }
            ]
        }
    )

    assert total == 1
    assert "avoid repo-wide searches" in prompt
    assert "use `ls` or `glob` first" in prompt
    assert "narrow `path` before `grep`" in prompt


def test_builtin_grep_tool_description_discourages_global_search() -> None:
    route_source = (Path(__file__).parents[1] / "src/api/routes/agent/__init__.py").read_text(
        encoding="utf-8"
    )

    assert 'name="grep"' in route_source
    assert "避免全局搜索" in route_source
    assert "先缩小路径范围" in route_source


def test_deferred_manager_applies_disabled_mcp_tools() -> None:
    manager = DeferredToolManager(
        all_deferred_tools=[
            _FakeTool("github:create_issue", "Create issue", server="github"),
            _FakeTool("slack:send", "Send Slack message", server="slack"),
            _FakeTool("notion:query", "Query Notion", server="notion"),
        ],
        session_id="session-1",
        disabled_mcp_tools=["github:create_issue", "mcp:slack"],
    )

    assert manager.get_tool("github:create_issue") is None
    assert manager.get_tool("slack:send") is None
    assert manager.get_tool("notion:query") is not None


@pytest.mark.asyncio
async def test_fetch_and_format_returns_empty_when_mcporter_is_unavailable() -> None:
    class _Result:
        def __init__(self, exit_code: int, output: str) -> None:
            self.exit_code = exit_code
            self.output = output

    class _Backend:
        def __init__(self) -> None:
            self.commands: list[tuple[str, int]] = []

        async def aexecute(self, command: str, *, timeout: int | None = None) -> _Result:
            self.commands.append((command, timeout or 0))
            if command == "mcporter --version":
                return _Result(127, "/bin/bash: mcporter: command not found")
            raise AssertionError(f"unexpected command: {command}")

    backend = _Backend()

    sections, total = await _fetch_and_format(backend)

    assert sections == ()
    assert total == 0
    assert backend.commands == [("mcporter --version", 5)]


@pytest.mark.asyncio
async def test_fetch_and_format_lists_tools_when_mcporter_is_available() -> None:
    class _Result:
        def __init__(self, exit_code: int, output: str) -> None:
            self.exit_code = exit_code
            self.output = output

    class _Backend:
        def __init__(self) -> None:
            self.commands: list[tuple[str, int]] = []

        async def aexecute(self, command: str, *, timeout: int | None = None) -> _Result:
            self.commands.append((command, timeout or 0))
            if command == "mcporter --version":
                return _Result(0, "mcporter 1.2.3")
            if command == "mcporter list --json":
                return _Result(
                    0,
                    '{"servers":[{"name":"playwright","status":"ok","tools":[{"name":"screenshot","description":"Take a screenshot.","inputSchema":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}}]}]}',
                )
            raise AssertionError(f"unexpected command: {command}")

    backend = _Backend()

    sections, total = await _fetch_and_format(backend)

    assert total == 1
    assert len(sections) == 2
    assert backend.commands == [("mcporter --version", 5), ("mcporter list --json", 15)]
