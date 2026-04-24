import json
from types import SimpleNamespace

import pytest

from src.infra.tool.sandbox_mcp_tool import get_sandbox_mcp_tools


class _Runtime:
    def __init__(self, user_id: str | None, backend=None) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {"configurable": {"context": context}}
        if backend is not None:
            self.config["configurable"]["backend"] = backend


def test_get_sandbox_mcp_tools_returns_three_tools_with_runtime_injected() -> None:
    tools = get_sandbox_mcp_tools()

    assert [t.name for t in tools] == [
        "sandbox_mcp_add",
        "sandbox_mcp_update",
        "sandbox_mcp_remove",
    ]

    for tool in tools:
        assert "runtime" in tool.get_input_schema().model_fields, (
            f"{tool.name}: 'runtime' must be in inferred args_schema so InjectedToolArg works"
        )
        assert hasattr(tool, "_injected_args_keys") and "runtime" in tool._injected_args_keys, (
            f"{tool.name}: 'runtime' not in _injected_args_keys — ToolRuntime injection will fail"
        )


def test_sandbox_mcp_add_exposes_expected_user_params() -> None:
    tools = {t.name: t for t in get_sandbox_mcp_tools()}
    schema = tools["sandbox_mcp_add"].get_input_schema().model_fields

    assert "server_name" in schema
    assert "command" in schema
    assert "env_keys" in schema


def test_sandbox_mcp_update_exposes_expected_user_params() -> None:
    tools = {t.name: t for t in get_sandbox_mcp_tools()}
    schema = tools["sandbox_mcp_update"].get_input_schema().model_fields

    assert "server_name" in schema
    assert "command" in schema
    assert "env_keys" in schema


def test_sandbox_mcp_remove_exposes_expected_user_params() -> None:
    tools = {t.name: t for t in get_sandbox_mcp_tools()}
    schema = tools["sandbox_mcp_remove"].get_input_schema().model_fields

    assert "server_name" in schema


@pytest.mark.asyncio
async def test_sandbox_mcp_add_returns_error_without_backend() -> None:
    from src.infra.tool import sandbox_mcp_tool

    result = json.loads(
        await sandbox_mcp_tool._mcporter_add(_Runtime("user-1"), "test-srv", "npx fake")
    )

    assert result["error"] == "No sandbox backend available"


@pytest.mark.asyncio
async def test_sandbox_mcp_remove_returns_error_without_backend() -> None:
    from src.infra.tool import sandbox_mcp_tool

    result = json.loads(await sandbox_mcp_tool._mcporter_remove(_Runtime("user-1"), "test-srv"))

    assert result["error"] == "No sandbox backend available"
