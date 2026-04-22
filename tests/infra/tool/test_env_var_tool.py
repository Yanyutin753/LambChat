import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import SystemMessage

from src.kernel.schemas.envvar import EnvVarResponse


class _Runtime:
    def __init__(self, user_id: str | None, backend=None) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {"configurable": {"context": context}}
        if backend is not None:
            self.config["configurable"]["backend"] = backend


class _FakeEnvVarStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, object | None]] = []

    async def list_vars(self, user_id: str) -> list[EnvVarResponse]:
        self.calls.append(("list", user_id, None))
        return [
            EnvVarResponse(
                key="FIRECRAWL_API_KEY",
                value="***",
                created_at="2026-04-23T00:00:00+00:00",
                updated_at="2026-04-23T00:00:00+00:00",
            )
        ]

    async def set_var(self, user_id: str, key: str, value: str) -> EnvVarResponse:
        self.calls.append(("set", user_id, (key, value)))
        return EnvVarResponse(key=key, value="***", updated_at="2026-04-23T00:00:00+00:00")

    async def delete_var(self, user_id: str, key: str) -> bool:
        self.calls.append(("delete", user_id, key))
        return key == "FIRECRAWL_API_KEY"

    async def delete_all_vars(self, user_id: str) -> int:
        self.calls.append(("delete_all", user_id, None))
        return 2


class _Request:
    def __init__(self, system_message):
        self.system_message = system_message

    def override(self, **kwargs):
        return _Request(kwargs.get("system_message", self.system_message))


def _load_module_from_path(module_name: str, relative_path: str):
    path = Path(__file__).parents[3] / relative_path
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _stub_context_tool_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    def tool(name: str):
        return SimpleNamespace(name=name)

    monkeypatch.setitem(
        sys.modules,
        "src.infra.tool.human_tool",
        SimpleNamespace(get_human_tool=lambda session_id=None: tool("ask_human")),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.tool.reveal_file_tool",
        SimpleNamespace(get_reveal_file_tool=lambda: tool("reveal_file")),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.tool.reveal_project_tool",
        SimpleNamespace(get_reveal_project_tool=lambda: tool("reveal_project")),
    )
    monkeypatch.setitem(
        sys.modules,
        "src.infra.tool.transfer_file_tool",
        SimpleNamespace(
            get_transfer_file_tool=lambda: tool("transfer_file"),
            get_transfer_path_tool=lambda: tool("transfer_path"),
        ),
    )


def test_get_env_var_tools_returns_safe_crud_tools() -> None:
    from src.infra.tool.env_var_tool import get_env_var_tools

    tools = get_env_var_tools()

    assert [tool.name for tool in tools] == [
        "env_var_list",
        "env_var_set",
        "env_var_delete",
        "env_var_delete_all",
    ]
    assert tools[0].args == {}
    assert "runtime" not in tools[1].args


@pytest.mark.asyncio
async def test_env_var_prompt_lists_keys_without_values(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.tool import env_var_prompt

    storage = _FakeEnvVarStorage()
    monkeypatch.setattr(env_var_prompt, "EnvVarStorage", lambda: storage)
    env_var_prompt.invalidate_env_var_prompt_cache("user-1")

    prompt = await env_var_prompt.build_env_var_prompt("user-1")

    assert "## Available Environment Variables" in prompt
    assert "`FIRECRAWL_API_KEY`" in prompt
    assert "$FIRECRAWL_API_KEY" in prompt
    assert "os.environ" in prompt
    assert "super-secret-value" not in prompt
    assert "value" not in prompt.lower()


@pytest.mark.asyncio
async def test_env_var_prompt_middleware_appends_key_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.agent import middleware

    async def fake_build_env_var_prompt(user_id: str) -> str:
        assert user_id == "user-1"
        return "## Available Environment Variables\n- `FIRECRAWL_API_KEY`"

    monkeypatch.setattr(middleware, "build_env_var_prompt", fake_build_env_var_prompt)

    captured = []

    async def handler(request):
        captured.append(request)
        return "ok"

    result = await middleware.EnvVarPromptMiddleware(user_id="user-1").awrap_model_call(
        _Request(SystemMessage(content="base")),
        handler,
    )

    assert result == "ok"
    assert "FIRECRAWL_API_KEY" in str(captured[0].system_message.content)


@pytest.mark.asyncio
async def test_env_var_list_returns_masked_values(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.tool import env_var_tool

    storage = _FakeEnvVarStorage()
    monkeypatch.setattr(env_var_tool, "EnvVarStorage", lambda: storage)

    result = json.loads(await env_var_tool._env_var_list(_Runtime("user-1")))

    assert result["count"] == 1
    assert result["variables"][0]["key"] == "FIRECRAWL_API_KEY"
    assert result["variables"][0]["value"] == "***"
    assert storage.calls == [("list", "user-1", None)]


@pytest.mark.asyncio
async def test_env_var_set_delegates_to_storage_and_masks_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import env_var_tool

    storage = _FakeEnvVarStorage()
    monkeypatch.setattr(env_var_tool, "EnvVarStorage", lambda: storage)

    result = json.loads(
        await env_var_tool._env_var_set(_Runtime("user-1"), "FIRECRAWL_API_KEY", "secret")
    )

    assert result["success"] is True
    assert result["variable"]["key"] == "FIRECRAWL_API_KEY"
    assert result["variable"]["value"] == "***"
    assert "secret" not in json.dumps(result)
    assert storage.calls == [("set", "user-1", ("FIRECRAWL_API_KEY", "secret"))]


@pytest.mark.asyncio
async def test_env_var_set_invalidates_prompt_and_syncs_current_sandbox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.tool import env_var_tool

    storage = _FakeEnvVarStorage()
    sync_calls: list[tuple[object, str]] = []
    invalidated: list[str] = []
    backend = object()

    async def fake_sync(current_backend: object, user_id: str) -> None:
        sync_calls.append((current_backend, user_id))

    monkeypatch.setattr(env_var_tool, "EnvVarStorage", lambda: storage)
    monkeypatch.setattr(env_var_tool, "ensure_sandbox_mcp", fake_sync)
    monkeypatch.setattr(env_var_tool, "invalidate_env_var_prompt_cache", invalidated.append)

    await env_var_tool._env_var_set(
        _Runtime("user-1", backend=backend), "FIRECRAWL_API_KEY", "secret"
    )

    assert sync_calls == [(backend, "user-1")]
    assert invalidated == ["user-1"]


@pytest.mark.asyncio
async def test_env_var_delete_delegates_to_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.tool import env_var_tool

    storage = _FakeEnvVarStorage()
    monkeypatch.setattr(env_var_tool, "EnvVarStorage", lambda: storage)

    result = json.loads(await env_var_tool._env_var_delete(_Runtime("user-1"), "FIRECRAWL_API_KEY"))

    assert result == {
        "success": True,
        "message": "Environment variable 'FIRECRAWL_API_KEY' deleted",
    }
    assert storage.calls == [("delete", "user-1", "FIRECRAWL_API_KEY")]


@pytest.mark.asyncio
async def test_env_var_tool_requires_runtime_user() -> None:
    from src.infra.tool import env_var_tool

    result = json.loads(await env_var_tool._env_var_list(_Runtime(None)))

    assert result == {"error": "No user context available"}


@pytest.mark.asyncio
async def test_search_agent_context_includes_env_var_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_context_tool_imports(monkeypatch)
    search_context = _load_module_from_path(
        "search_context_under_test",
        "src/agents/search_agent/context.py",
    )

    monkeypatch.setattr(search_context.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(search_context.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(search_context.settings, "ENABLE_SKILLS", False)

    ctx = search_context.SearchAgentContext(user_id="user-1")
    await ctx.setup()

    names = {tool.name for tool in ctx.tools}
    assert {"env_var_list", "env_var_set", "env_var_delete", "env_var_delete_all"} <= names


@pytest.mark.asyncio
async def test_fast_agent_context_includes_env_var_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_context_tool_imports(monkeypatch)
    fast_context = _load_module_from_path(
        "fast_context_under_test",
        "src/agents/fast_agent/context.py",
    )

    monkeypatch.setattr(fast_context.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(fast_context.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(fast_context.settings, "ENABLE_SKILLS", False)

    ctx = fast_context.FastAgentContext(user_id="user-1")
    await ctx.setup()

    names = {tool.name for tool in ctx.tools}
    assert {"env_var_list", "env_var_set", "env_var_delete", "env_var_delete_all"} <= names
