from src.infra.tool.deferred_manager import DeferredToolManager
from src.infra.tool.sandbox_mcp_prompt import _format_tools_list


class _FakeTool:
    def __init__(self, name: str, description: str, server: str = "") -> None:
        self.name = name
        self.description = description
        self.server = server


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
