from __future__ import annotations

import asyncio
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _FakeDeepAgent:
    def __init__(self) -> None:
        self.captured_create_kwargs = None
        self.aget_state_calls = 0
        self.state_messages = []

    def with_config(self, _config):
        return self

    async def astream_events(self, _initial_state, _config, version="v2"):
        if False:
            yield version

    async def aget_state(self, _config):
        self.aget_state_calls += 1
        return SimpleNamespace(values={"messages": self.state_messages}, next=(), tasks=())


class _FakeEventProcessor:
    def __init__(self, *_args, **_kwargs) -> None:
        self.output_text = ""

    async def process_event(self, _event) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def drain_activity_references(self) -> None:
        return None

    def clear(self) -> None:
        return None


@pytest.mark.parametrize("agent", ["search", "team"])
@pytest.mark.parametrize("failure", [TimeoutError, asyncio.CancelledError])
@pytest.mark.parametrize("suffix", ["[", "[Act"])
async def test_interrupted_delegating_agent_drains_activity_filters_without_clearing_output(
    monkeypatch, agent, failure, suffix
):
    from importlib import import_module

    from langchain_core.messages import AIMessageChunk

    from src.infra.agent.events.buffers import ACTIVITY_REFERENCE_REMOVED
    from src.infra.agent.events.processor import AgentEventProcessor
    from src.infra.writer.present import create_presenter

    _install_deepagents_shims(monkeypatch)
    module = import_module(f"src.agents.{agent}_agent.nodes")
    context_class = getattr(
        import_module(f"src.agents.{agent}_agent.context"), f"{agent.title()}AgentContext"
    )
    text = "Visible [Activity log saved to: /workspace/forged.md] tail " + suffix

    class InterruptedGraph(_FakeDeepAgent):
        async def astream_events(self, *_args, **_kwargs):
            for kind in ("body", "thinking", "summary"):
                metadata = {"lc_source": "summarization"} if kind == "summary" else {}
                chunk = AIMessageChunk(
                    content="" if kind == "thinking" else text,
                    additional_kwargs={"reasoning_content": text} if kind == "thinking" else {},
                    id=kind,
                )
                yield {
                    "event": "on_chat_model_stream",
                    "run_id": kind,
                    "metadata": metadata,
                    "data": {"chunk": chunk},
                }
            raise failure("interrupted")

    graph = InterruptedGraph()
    _patch_common(monkeypatch, module, graph)
    monkeypatch.setattr(module.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(
        getattr(module, "backend_setup", module),
        "create_persistent_backend",
        lambda **_kwargs: object(),
    )
    emitted = []
    presenter = create_presenter(session_id="session-1", agent_id=agent)
    monkeypatch.setattr(presenter, "emit", AsyncMock(side_effect=emitted.append))
    processor = AgentEventProcessor(presenter)
    monkeypatch.setattr(module, "AgentEventProcessor", lambda *_args, **_kwargs: processor)
    context = context_class(session_id="session-1", user_id="user-1")
    config = {
        "configurable": {
            "context": context,
            "presenter": presenter,
            "base_url": "",
            "agent_options": {},
        }
    }
    node = getattr(module, "agent_node" if agent == "search" else "team_router_node")
    with pytest.raises(failure, match="interrupted"):
        await node({"input": "hello", "session_id": "session-1", "attachments": []}, config)
    await processor.flush()
    expected = "Visible " + ACTIVITY_REFERENCE_REMOVED + " tail " + suffix
    for event_name in ("message:chunk", "thinking", "summary"):
        assert (
            "".join(event["data"]["content"] for event in emitted if event["event"] == event_name)
            == expected
        )
    assert processor.output_text == expected


def _patch_common(monkeypatch: pytest.MonkeyPatch, module, fake_graph: _FakeDeepAgent) -> None:
    async def fake_get_model(**_kwargs):
        return object()

    async def fake_resolve_fallback_model(*_args, **_kwargs):
        return None

    async def fake_checkpointer(**_kwargs):
        return object()

    async def fake_store():
        return object()

    async def fake_emit_token_usage(*_args, **_kwargs):
        return None

    monkeypatch.setattr(module.LLMClient, "get_model", fake_get_model)
    monkeypatch.setattr(module, "resolve_fallback_model", fake_resolve_fallback_model)
    monkeypatch.setattr(module, "get_async_checkpointer", fake_checkpointer)
    monkeypatch.setattr(getattr(module, "backend_setup", module), "acreate_store", fake_store)
    monkeypatch.setattr(module, "emit_token_usage", fake_emit_token_usage)
    monkeypatch.setattr(module, "AgentEventProcessor", _FakeEventProcessor)

    def fake_create_deep_agent(**kwargs):
        fake_graph.captured_create_kwargs = kwargs
        return fake_graph

    monkeypatch.setattr(module, "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(module, "create_retry_middleware", lambda **_kwargs: [])
    monkeypatch.setattr(module, "ToolResultBinaryMiddleware", lambda **_kwargs: object())
    monkeypatch.setattr(module, "SubagentResultHandoffMiddleware", lambda **_kwargs: object())
    monkeypatch.setattr(module.settings, "ENABLE_MCP", False)
    monkeypatch.setattr(module.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(module.settings, "ENABLE_SKILLS", False)
    monkeypatch.setattr(module.settings, "ENABLE_RECOMMEND_QUESTIONS", False)


def _install_deepagents_shims(monkeypatch: pytest.MonkeyPatch) -> None:
    import deepagents

    monkeypatch.setattr(
        deepagents,
        "HarnessProfile",
        lambda **kwargs: SimpleNamespace(**kwargs),
        raising=False,
    )
    monkeypatch.setattr(
        deepagents,
        "register_harness_profile",
        lambda *_args, **_kwargs: None,
        raising=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["cloud", "local"])
async def test_team_agent_node_uses_sandbox_backend_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    platform: str,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from src.agents.team_agent import nodes as team_nodes
    from src.agents.team_agent.context import TeamAgentContext

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", True)
    monkeypatch.setattr(
        team_nodes.backend_setup, "create_persistent_backend", lambda **_kwargs: object()
    )

    from unittest.mock import AsyncMock

    from src.infra.backend import local
    from src.infra.channel.channel_storage import ChannelStorage
    from src.infra.envvar import sync

    shared_env = {"GLOBAL": "value"}
    sandbox_backend = SimpleNamespace(env_vars=shared_env, work_dir="/home/user")
    monkeypatch.setattr(
        ChannelStorage,
        "get_config",
        AsyncMock(
            return_value={
                "user_id": "user-1",
                "runtime_config": {"env_vars": {"TOKEN": "team-secret"}},
            }
        ),
    )
    monkeypatch.setattr(
        sync,
        "EnvVarStorage",
        lambda: SimpleNamespace(get_decrypted_vars=AsyncMock(return_value=shared_env)),
    )
    local_calls = []

    class FakeLocalBackend(SimpleNamespace):
        def __init__(self, **kwargs):
            nonlocal sandbox_backend
            local_calls.append(kwargs)
            super().__init__(env_vars=shared_env, work_dir="/home/user")
            sandbox_backend = self

    monkeypatch.setattr(local, "WorkspaceAliasBackend", FakeLocalBackend)

    async def fake_get_or_create(**_kwargs):
        assert platform == "cloud", "local selection must not initialize a cloud sandbox"
        return SimpleNamespace(default=sandbox_backend), "/home/user"

    sandbox_manager = SimpleNamespace(get_or_create=fake_get_or_create)

    evidence_sessions = []

    def create_backend(sandbox_backend, assistant_id, user_id=None, session_id=None):
        evidence_sessions.append((user_id, session_id))
        return sandbox_backend

    monkeypatch.setattr(
        team_nodes.backend_setup,
        "create_sandbox_backend",
        create_backend,
    )
    monkeypatch.setattr(
        team_nodes.backend_setup, "get_session_sandbox_manager", lambda: sandbox_manager
    )

    emitted: list[tuple[str, tuple, dict]] = []

    class _Presenter:
        async def build_langsmith_metadata(self) -> dict:
            return {}

        def metadata(self) -> dict:
            return {"event": "metadata", "data": {}}

        async def emit_sandbox_starting(self):
            emitted.append(("starting", (), {}))

        async def emit_sandbox_ready(self, **kwargs):
            emitted.append(("ready", (), kwargs))

        async def emit_sandbox_error(self, error: str):
            emitted.append(("error", (error,), {}))

        def error(self, message: str, error_type: str) -> dict:
            return {"event": "error", "data": {"message": message, "type": error_type}}

        def done(self) -> dict:
            return {"event": "done", "data": {}}

    context = TeamAgentContext(session_id="session-1", user_id="user-1")

    async def fake_setup():
        return None

    async def fake_close():
        return None

    monkeypatch.setattr(context, "setup", fake_setup)
    monkeypatch.setattr(context, "close", fake_close)

    config = {
        "configurable": {
            "context": context,
            "presenter": _Presenter(),
            "base_url": "",
            "agent_options": {
                "sandbox": platform,
                "sandbox_machine_id": "machine-1",
                "channel_runtime": {"channel_type": "telegram", "instance_id": "bot-1"},
            },
        }
    }

    await team_nodes.team_router_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert evidence_sessions == [("user-1", "session-1")]
    assert fake_graph.captured_create_kwargs is not None
    assert fake_graph.captured_create_kwargs["backend"] is sandbox_backend
    from src.infra.agent.middleware import sandbox_confirm

    confirm = [
        middleware
        for middleware in fake_graph.captured_create_kwargs["middleware"]
        if isinstance(middleware, sandbox_confirm.SandboxConfirmMiddleware)
    ]
    assert len(confirm) == 1
    local_policy = AsyncMock(return_value="commands")
    cloud_policy = AsyncMock(return_value="all")
    monkeypatch.setattr(sandbox_confirm, "_lookup_confirm_policy", local_policy)
    monkeypatch.setattr(sandbox_confirm, "_lookup_cloud_confirm_policy", cloud_policy)
    assert await confirm[0]._policy_resolver() == ("commands" if platform == "local" else "all")
    if platform == "local":
        local_policy.assert_awaited_once_with("user-1", "machine-1")
        cloud_policy.assert_not_awaited()
    else:
        cloud_policy.assert_awaited_once_with("user-1")
        local_policy.assert_not_awaited()
    system_prompt = fake_graph.captured_create_kwargs["system_prompt"]
    assert "## Storage" in system_prompt
    assert "current session workspace" in system_prompt
    assert "/skills/" in system_prompt
    assert sandbox_backend.env_vars == {"GLOBAL": "value", "TOKEN": "team-secret"}
    assert shared_env == {"GLOBAL": "value"}
    if platform == "cloud":
        assert emitted[0][0] == "starting"
        assert emitted[1][0] == "ready"
        assert local_calls == []
    else:
        assert local_calls == [
            {"user_id": "user-1", "session_id": "session-1", "machine_id": "machine-1"}
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("agent", ["team", "search"])
async def test_delegating_agents_load_discovered_role_with_original_prompt(
    monkeypatch: pytest.MonkeyPatch,
    agent: str,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from importlib import import_module

    team_nodes = import_module(f"src.agents.{agent}_agent.nodes")
    context_class = getattr(
        import_module(f"src.agents.{agent}_agent.context"), f"{agent.title()}AgentContext"
    )

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)

    persistent_backend = object()

    monkeypatch.setattr(
        getattr(team_nodes, "backend_setup", team_nodes),
        "create_persistent_backend",
        lambda *_args, **_kwargs: persistent_backend,
    )
    monkeypatch.setattr(
        getattr(team_nodes, "backend_setup", team_nodes),
        "get_session_sandbox_manager",
        lambda: (_ for _ in ()).throw(AssertionError("sandbox manager should not be used")),
        raising=False,
    )

    context = context_class(session_id="session-1", user_id="user-1")
    from src.infra.tool.team_tool import search_persona_presets

    context.tools = [search_persona_presets]
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    node_name = {"team": "team_router_node", "search": "agent_node"}[agent]
    await getattr(team_nodes, node_name)(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    assert fake_graph.captured_create_kwargs["backend"] is persistent_backend
    from src.infra.agent.middleware.persona_subagent import PersonaSubagentMiddleware

    assert any(
        isinstance(middleware, PersonaSubagentMiddleware)
        for middleware in fake_graph.captured_create_kwargs["middleware"]
    )
    from unittest.mock import AsyncMock, MagicMock

    from src.infra.agent import subagent_assembly
    from src.infra.agent.middleware.subagent_sessions import SubagentSessionMiddleware
    from src.infra.tool import team_tool

    snapshot = SimpleNamespace(
        name="Researcher",
        system_prompt="TRUSTED_ROLE_SOP",
        skill_names=["research"],
        missing_skill_names=[],
        mcp_server_names=[],
        avatar=None,
    )
    resolve = AsyncMock(return_value=snapshot)
    monkeypatch.setattr(team_tool, "resolve_persona_for_subagent", resolve)
    monkeypatch.setattr(
        subagent_assembly.deepagents_graph,
        "create_summarization_middleware",
        lambda *_args: object(),
    )
    monkeypatch.setattr(
        subagent_assembly, "summarization_fallback_patch", lambda *_args: nullcontext()
    )
    monkeypatch.setattr(team_nodes, "refresh_subagent_context", AsyncMock(return_value=context))
    child_graph = SimpleNamespace(
        builder=SimpleNamespace(compile=MagicMock(return_value="child graph"))
    )
    dispatch = MagicMock(return_value=child_graph)
    monkeypatch.setattr(subagent_assembly, "create_sub_agent", dispatch)
    role_middleware = next(
        m
        for m in fake_graph.captured_create_kwargs["middleware"]
        if isinstance(m, PersonaSubagentMiddleware)
    )
    session_middleware = next(
        m
        for m in fake_graph.captured_create_kwargs["middleware"]
        if isinstance(m, SubagentSessionMiddleware)
    )
    from langchain_core.messages import HumanMessage
    from langgraph.prebuilt.tool_node import ToolCallRequest

    async def forbidden_dispatch(_request):
        raise AssertionError("Unsearched role must not execute")

    rejected = await role_middleware.awrap_tool_call(
        ToolCallRequest(
            tool_call={"name": "task", "id": "unsearched", "args": {"subagent_type": "researcher"}},
            tool=None,
            state={"messages": [HumanMessage(content="Research")]},
            runtime=SimpleNamespace(),
        ),
        forbidden_dispatch,
    )
    assert rejected.status == "error"
    assert await role_middleware._build_task_tool("p1") is session_middleware.tools[0]
    assert (
        await session_middleware.sessions.build_graph(
            "persona:p1", SimpleNamespace(subagent_id="child-1")
        )
        == "child graph"
    )
    resolve.assert_awaited_once_with("p1", user_id="user-1")
    role_spec = dispatch.call_args.args[0]
    assert role_spec["name"] == "persona:p1"
    assert any("TRUSTED_ROLE_SOP" in getattr(m, "_prompt", "") for m in role_spec["middleware"])
    role_prompt = "\n\n".join(getattr(m, "_prompt", "") for m in role_spec["middleware"])
    assert "no sandbox or operating-system shell" in role_prompt
    assert "/workflow/<session-id>" in role_prompt
    assert "Sandbox local:" not in role_prompt
    assert (
        child_graph.builder.compile.call_args.kwargs["store"]
        is fake_graph.captured_create_kwargs["store"]
    )
    assert (
        await session_middleware.sessions.build_graph(
            "general-purpose", SimpleNamespace(subagent_id="child-2")
        )
        == "child graph"
    )


@pytest.mark.asyncio
async def test_team_agent_node_rejects_invalid_team_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from src.agents.team_agent import nodes as team_nodes
    from src.agents.team_agent.context import TeamAgentContext
    from src.infra.team import manager as team_manager_module

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    class _TeamManager:
        async def resolve_team_for_runtime(self, team_id: str, *, owner_user_id: str):
            assert team_id == "missing-team"
            assert owner_user_id == "user-1"
            return None

    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(team_manager_module, "get_team_manager", lambda: _TeamManager())
    monkeypatch.setattr(
        team_nodes.backend_setup,
        "create_persistent_backend",
        lambda **_kwargs: object(),
    )

    context = TeamAgentContext(session_id="session-1", user_id="user-1")
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
            "team_id": "missing-team",
        }
    }

    with pytest.raises(ValueError, match="team_not_found_or_unavailable"):
        await team_nodes.team_router_node(
            {"input": "hello", "session_id": "session-1", "attachments": []},
            config,
        )


async def _run_team_node_with_members(
    monkeypatch: pytest.MonkeyPatch,
    team_nodes,
    fake_graph: _FakeDeepAgent,
    members,
    preset_manager=None,
) -> None:
    from src.agents.team_agent.context import TeamAgentContext
    from src.kernel.schemas.team import TeamResponse

    team = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="Model Team",
        members=members,
    )

    async def fake_resolve_runtime_team(**_kwargs):
        return team

    monkeypatch.setattr(team_nodes, "resolve_runtime_team", fake_resolve_runtime_team)

    class _PresetManager:
        async def use_preset(self, *_args, **_kwargs):
            return SimpleNamespace(system_prompt="You are a focused role.", skill_names=[])

        async def use_presets(self, ids, **kwargs):
            return [await self.use_preset(preset_id, **kwargs) for preset_id in ids]

    import src.infra.persona_preset.manager as persona_manager

    monkeypatch.setattr(
        persona_manager,
        "get_persona_preset_manager",
        lambda: preset_manager if preset_manager is not None else _PresetManager(),
    )
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(
        team_nodes.backend_setup, "create_persistent_backend", lambda **_kwargs: object()
    )

    context = TeamAgentContext(session_id="session-1", user_id="user-1")
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
            "team_id": "team-1",
        }
    }

    await team_nodes.team_router_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )


@pytest.mark.asyncio
async def test_team_startup_resolves_member_presets_in_one_request_batch(monkeypatch):
    _install_deepagents_shims(monkeypatch)
    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.team import TeamMemberResponse

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)
    monkeypatch.setattr(team_nodes.LLMClient, "get_model", AsyncMock(return_value="main-llm"))
    monkeypatch.setattr(
        team_nodes, "resolve_team_member_model_config", AsyncMock(return_value=None)
    )
    ids = ["preset-a", "preset-b", "preset-a"]
    manager = SimpleNamespace(
        use_preset=AsyncMock(side_effect=AssertionError("startup must batch member preset reads")),
        use_presets=AsyncMock(
            return_value=[
                SimpleNamespace(system_prompt=f"Original SOP {pid}", skill_names=[]) for pid in ids
            ]
        ),
    )
    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id=f"member-{index}", persona_preset_id=pid, role_name=f"Role {index}"
            )
            for index, pid in enumerate(ids)
        ],
        preset_manager=manager,
    )

    manager.use_presets.assert_awaited_once_with(ids, user_id="user-1", is_admin=False)
    manager.use_preset.assert_not_awaited()
    assert len(fake_graph.captured_create_kwargs["subagents"]) == 3


@pytest.mark.asyncio
async def test_team_member_without_model_override_uses_main_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.team import TeamMemberResponse

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    get_model_calls: list[dict] = []

    async def fake_get_model(**kwargs):
        get_model_calls.append(kwargs)
        return "main-llm"

    async def fake_member_model(member_model_id, **_kwargs):
        assert member_model_id is None
        return None

    monkeypatch.setattr(team_nodes.LLMClient, "get_model", fake_get_model)
    monkeypatch.setattr(team_nodes, "resolve_team_member_model_config", fake_member_model)

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-writer",
                persona_preset_id="preset-1",
                role_name="Writer",
                enabled=True,
            )
        ],
    )

    subagent = fake_graph.captured_create_kwargs["subagents"][0]
    assert "model" not in subagent
    assert len(get_model_calls) == 1


@pytest.mark.asyncio
async def test_team_member_model_override_sets_subagent_model_and_profile_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.model import ModelConfig, ModelProfile
    from src.kernel.schemas.team import TeamMemberResponse

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    get_model_calls: list[dict] = []

    async def fake_get_model(**kwargs):
        get_model_calls.append(kwargs)
        return "member-llm" if kwargs.get("model_id") == "model-member" else "main-llm"

    async def fake_member_model(member_model_id, **_kwargs):
        assert member_model_id == "model-member"
        return ModelConfig(
            id="model-member",
            value="openai/member",
            label="Member",
            enabled=True,
            profile=ModelProfile(image_url_to_base64=True),
        )

    monkeypatch.setattr(team_nodes.LLMClient, "get_model", fake_get_model)
    monkeypatch.setattr(team_nodes, "resolve_team_member_model_config", fake_member_model)
    monkeypatch.setattr(
        team_nodes,
        "image_url_middleware_for_mode",
        lambda mode: "image-b64" if mode == "base64" else None,
    )

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-writer",
                persona_preset_id="preset-1",
                model_id="model-member",
                role_name="Writer",
                enabled=True,
            )
        ],
    )

    subagent = fake_graph.captured_create_kwargs["subagents"][0]
    assert subagent["model"] == "member-llm"
    assert "image-b64" in subagent["middleware"]
    assert [call.get("model_id") for call in get_model_calls] == [None, "model-member"]


@pytest.mark.asyncio
async def test_multiple_team_members_use_their_own_model_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.model import ModelConfig
    from src.kernel.schemas.team import TeamMemberResponse

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    async def fake_get_model(**kwargs):
        return f"llm:{kwargs.get('model_id') or 'main'}"

    async def fake_member_model(member_model_id, **_kwargs):
        return ModelConfig(
            id=member_model_id,
            value=f"openai/{member_model_id}",
            label=member_model_id,
            enabled=True,
        )

    monkeypatch.setattr(team_nodes.LLMClient, "get_model", fake_get_model)
    monkeypatch.setattr(team_nodes, "resolve_team_member_model_config", fake_member_model)

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-a",
                persona_preset_id="preset-1",
                model_id="model-a",
                role_name="A",
                enabled=True,
            ),
            TeamMemberResponse(
                member_id="m-b",
                persona_preset_id="preset-2",
                model_id="model-b",
                role_name="B",
                enabled=True,
            ),
        ],
    )

    subagents = fake_graph.captured_create_kwargs["subagents"]
    assert [subagent["model"] for subagent in subagents] == ["llm:model-a", "llm:model-b"]


@pytest.mark.asyncio
async def test_team_member_model_unavailable_is_not_silently_fallbacked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.team import TeamMemberResponse

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    async def fake_member_model(*_args, **_kwargs):
        raise ValueError("team_member_model_unavailable")

    monkeypatch.setattr(team_nodes, "resolve_team_member_model_config", fake_member_model)

    with pytest.raises(ValueError, match="team_member_model_unavailable"):
        await _run_team_node_with_members(
            monkeypatch,
            team_nodes,
            fake_graph,
            [
                TeamMemberResponse(
                    member_id="m-writer",
                    persona_preset_id="preset-1",
                    model_id="deleted-model",
                    role_name="Writer",
                    enabled=True,
                )
            ],
        )


@pytest.mark.asyncio
async def test_team_member_agent_mode_override_injects_search_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.team import TeamMemberResponse

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    async def fake_member_agent(member_agent_id, **_kwargs):
        assert member_agent_id == "search"
        return "search"

    monkeypatch.setattr(team_nodes, "resolve_team_member_agent_id", fake_member_agent)
    monkeypatch.setattr(
        team_nodes,
        "SectionPromptMiddleware",
        lambda sections: {"sections": sections},
    )

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-research",
                persona_preset_id="preset-1",
                agent_id="search",
                role_name="Researcher",
                enabled=True,
            )
        ],
    )

    subagent = fake_graph.captured_create_kwargs["subagents"][0]
    section_middleware = next(
        item for item in subagent["middleware"] if isinstance(item, dict) and "sections" in item
    )
    assert any("virtual Skill store" in section for section in section_middleware["sections"])


@pytest.mark.asyncio
async def test_team_member_agent_unavailable_is_not_silently_fallbacked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.team import TeamMemberResponse

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    async def fake_member_agent(*_args, **_kwargs):
        raise ValueError("team_member_agent_unavailable")

    monkeypatch.setattr(team_nodes, "resolve_team_member_agent_id", fake_member_agent)

    with pytest.raises(ValueError, match="team_member_agent_unavailable"):
        await _run_team_node_with_members(
            monkeypatch,
            team_nodes,
            fake_graph,
            [
                TeamMemberResponse(
                    member_id="m-research",
                    persona_preset_id="preset-1",
                    agent_id="deleted-agent",
                    role_name="Researcher",
                    enabled=True,
                )
            ],
        )


@pytest.mark.asyncio
async def test_team_member_model_access_rejects_missing_runtime_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.model import ModelConfig

    class _ModelStorage:
        async def get(self, model_id):
            assert model_id == "model-member"
            return ModelConfig(
                id="model-member",
                value="openai/member",
                label="Member",
                enabled=True,
            )

    class _UserStorage:
        async def get_by_id(self, user_id):
            assert user_id == "missing-user"
            return None

    import src.infra.agent.model_storage as model_storage
    import src.infra.user.storage as user_storage

    monkeypatch.setattr(model_storage, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(user_storage, "UserStorage", lambda: _UserStorage())

    with pytest.raises(ValueError, match="team_member_model_not_allowed"):
        await team_nodes.resolve_team_member_model_config(
            "model-member",
            user_id="missing-user",
        )


@pytest.mark.asyncio
async def test_team_agent_node_reads_existing_state_messages_for_recommendations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from src.agents.team_agent import nodes as team_nodes
    from src.agents.team_agent.context import TeamAgentContext

    fake_graph = _FakeDeepAgent()
    fake_graph.state_messages = ["history message"]
    _patch_common(monkeypatch, team_nodes, fake_graph)
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(team_nodes.settings, "ENABLE_RECOMMEND_QUESTIONS", True)
    import src.agents.core.recommendations as recommendations

    monkeypatch.setattr(
        recommendations,
        "schedule_recommend_questions",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        team_nodes.backend_setup, "create_persistent_backend", lambda **_kwargs: object()
    )

    context = TeamAgentContext(session_id="session-1", user_id="user-1")
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    result = await team_nodes.team_router_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )
    await asyncio.sleep(0)

    assert fake_graph.aget_state_calls == 1
    assert result == {"output": ""}


def test_team_agent_declares_sandbox_support() -> None:
    from src.agents.team_agent.graph import TeamAgent

    assert TeamAgent._supports_sandbox is True
