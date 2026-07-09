from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest


class _FakeDeepAgent:
    def __init__(self) -> None:
        self.captured_create_kwargs = None
        self.aget_state_calls = 0
        self.state_messages = []
        self.events = []
        self.events_by_call = None
        self.astream_events_calls = 0
        self.initial_states = []
        self.ainvoke_calls = 0
        self.ainvoke_inputs = []
        self.ainvoke_result_text = "forced delegation result"

    def with_config(self, _config):
        return self

    async def astream_events(self, initial_state, _config, version="v2"):
        self.astream_events_calls += 1
        self.initial_states.append(initial_state)
        events = self.events
        if self.events_by_call is not None:
            index = self.astream_events_calls - 1
            events = self.events_by_call[index] if index < len(self.events_by_call) else []
        for event in events:
            yield event
        if False:
            yield version

    async def aget_state(self, _config):
        self.aget_state_calls += 1
        return SimpleNamespace(values={"messages": self.state_messages})

    async def ainvoke(self, initial_state, _config):
        self.ainvoke_calls += 1
        self.ainvoke_inputs.append(initial_state)
        return {"messages": [SimpleNamespace(content=self.ainvoke_result_text)]}


class _FakeEventProcessor:
    def __init__(self, *_args, **_kwargs) -> None:
        self.output_text = ""

    async def process_event(self, _event) -> None:
        return None

    async def flush(self) -> None:
        return None

    def clear(self) -> None:
        return None

    def _append_output_text(self, text: str) -> None:
        self.output_text += text


def _patch_common(monkeypatch: pytest.MonkeyPatch, module, fake_graph: _FakeDeepAgent) -> None:
    module._test_get_model_calls = []

    async def fake_get_model(**_kwargs):
        module._test_get_model_calls.append(dict(_kwargs))
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
    monkeypatch.setattr(module, "acreate_store", fake_store)
    monkeypatch.setattr(module, "emit_token_usage", fake_emit_token_usage)
    monkeypatch.setattr(module, "AgentEventProcessor", _FakeEventProcessor)

    def fake_create_deep_agent(**kwargs):
        fake_graph.captured_create_kwargs = kwargs
        return fake_graph

    monkeypatch.setattr(module, "create_deep_agent", fake_create_deep_agent)
    monkeypatch.setattr(module, "create_retry_middleware", lambda **_kwargs: [])
    monkeypatch.setattr(module, "ToolResultBinaryMiddleware", lambda **_kwargs: object())
    monkeypatch.setattr(module, "SubagentResultHandoffMiddleware", lambda **_kwargs: object())
    monkeypatch.setattr(module, "PromptCachingMiddleware", lambda: object())
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
async def test_team_agent_node_uses_sandbox_backend_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
    from plugins.system.agent_team.backend.runtime.context import TeamAgentContext

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", True)
    monkeypatch.setattr(team_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

    sandbox_backend = object()

    def sandbox_factory(_runtime):
        return sandbox_backend

    async def fake_get_or_create(**_kwargs):
        return SimpleNamespace(default=sandbox_backend), "/home/user"

    sandbox_manager = SimpleNamespace(get_or_create=fake_get_or_create)

    monkeypatch.setattr(
        team_nodes,
        "create_sandbox_backend_factory",
        lambda sandbox_backend, assistant_id, user_id=None: sandbox_factory,
    )
    monkeypatch.setattr(team_nodes, "get_session_sandbox_manager", lambda: sandbox_manager)

    async def fake_resolve_runtime_team(**_kwargs):
        return TeamResponse(
            id="team-1",
            owner_user_id="user-1",
            name="Sandbox Team",
            run_in_sandbox=True,
        )

    monkeypatch.setattr(team_nodes, "resolve_runtime_team", fake_resolve_runtime_team)

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
            "agent_options": {},
            "team_id": "team-1",
        }
    }

    await team_nodes.team_router_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    assert fake_graph.captured_create_kwargs["backend"] is sandbox_backend
    assert "Storage Architecture (CRITICAL)" in fake_graph.captured_create_kwargs["system_prompt"]
    assert emitted[0][0] == "starting"
    assert emitted[1][0] == "ready"


@pytest.mark.asyncio
async def test_team_agent_node_uses_persistent_backend_when_team_sandbox_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
    from plugins.system.agent_team.backend.runtime.context import TeamAgentContext

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", True)

    persistent_backend = object()

    def persistent_factory(_runtime):
        return persistent_backend

    monkeypatch.setattr(
        team_nodes,
        "create_persistent_backend_factory",
        lambda **_kwargs: persistent_factory,
    )
    monkeypatch.setattr(
        team_nodes,
        "get_session_sandbox_manager",
        lambda: (_ for _ in ()).throw(AssertionError("sandbox manager should not be used")),
    )

    async def fake_resolve_runtime_team(**_kwargs):
        return TeamResponse(
            id="team-1",
            owner_user_id="user-1",
            name="Persistent Team",
            run_in_sandbox=False,
        )

    monkeypatch.setattr(team_nodes, "resolve_runtime_team", fake_resolve_runtime_team)

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

    assert fake_graph.captured_create_kwargs is not None
    assert fake_graph.captured_create_kwargs["backend"] is persistent_backend


@pytest.mark.asyncio
async def test_team_agent_node_uses_persistent_backend_when_sandbox_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
    from plugins.system.agent_team.backend.runtime.context import TeamAgentContext

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)

    persistent_backend = object()

    def persistent_factory(_runtime):
        return persistent_backend

    monkeypatch.setattr(
        team_nodes,
        "create_persistent_backend_factory",
        lambda **_kwargs: persistent_factory,
    )
    monkeypatch.setattr(
        team_nodes,
        "get_session_sandbox_manager",
        lambda: (_ for _ in ()).throw(AssertionError("sandbox manager should not be used")),
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

    await team_nodes.team_router_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    assert fake_graph.captured_create_kwargs["backend"] is persistent_backend


@pytest.mark.asyncio
async def test_team_agent_node_rejects_invalid_team_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain import manager as team_manager_module
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
    from plugins.system.agent_team.backend.runtime.context import TeamAgentContext

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
        team_nodes,
        "create_persistent_backend_factory",
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
    *,
    user_input: str = "hello",
) -> None:
    from plugins.system.agent_team.backend.domain.schemas import TeamResponse
    from plugins.system.agent_team.backend.runtime.context import TeamAgentContext

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

    import src.infra.persona_preset.manager as persona_manager

    monkeypatch.setattr(persona_manager, "get_persona_preset_manager", lambda: _PresetManager())
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(team_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

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
        {"input": user_input, "session_id": "session-1", "attachments": []},
        config,
    )


@pytest.mark.asyncio
async def test_team_router_forces_full_asset_package_delegation_after_router_noops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-storyboard",
                persona_preset_id="preset-1",
                role_name="分镜 Agent",
                enabled=True,
            )
        ],
        user_input="继续按完整素材包流程执行：分镜文案、每段提示词、首帧图和交付。",
    )
    assert fake_graph.astream_events_calls == 2
    assert fake_graph.ainvoke_calls == 1
    assert "Team router forced delegation recovery" in str(fake_graph.ainvoke_inputs[0])


@pytest.mark.asyncio
async def test_team_router_retries_full_asset_package_once_before_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    fake_graph.events_by_call = [
        [],
        [
            {
                "event": "on_tool_start",
                "name": "task",
                "data": {"input": {"subagent_type": "team-m-storyboard-agent"}},
            }
        ],
    ]
    _patch_common(monkeypatch, team_nodes, fake_graph)

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-storyboard",
                persona_preset_id="preset-1",
                role_name="分镜 Agent",
                enabled=True,
            )
        ],
        user_input="继续按完整素材包流程执行：分镜文案、每段提示词、首帧图和交付。",
    )

    assert fake_graph.astream_events_calls == 2
    assert "必须先调用 `task` 工具" in str(fake_graph.initial_states[1])
    assert "完整素材包流程" in str(fake_graph.initial_states[1])


@pytest.mark.asyncio
async def test_team_router_allows_full_asset_package_after_task_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    fake_graph.events = [
        {
            "event": "on_tool_start",
            "name": "task",
            "data": {"input": {"subagent_type": "team-m-storyboard-agent"}},
        }
    ]
    _patch_common(monkeypatch, team_nodes, fake_graph)

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-storyboard",
                persona_preset_id="preset-1",
                role_name="分镜 Agent",
                enabled=True,
            )
        ],
        user_input="继续按完整素材包流程执行：分镜文案、每段提示词、首帧图和交付。",
    )
    assert fake_graph.astream_events_calls == 1
    assert fake_graph.ainvoke_calls == 0


@pytest.mark.asyncio
async def test_team_router_forces_missing_members_after_partial_full_asset_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    fake_graph.events_by_call = [
        [
            {
                "event": "on_tool_start",
                "name": "task",
                "data": {"input": {"subagent_type": "team-m-manager-agent"}},
            }
        ]
    ]
    _patch_common(monkeypatch, team_nodes, fake_graph)

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-manager",
                persona_preset_id="preset-1",
                role_name="管理 Agent",
                enabled=True,
            ),
            TeamMemberResponse(
                member_id="m-copywriter",
                persona_preset_id="preset-1",
                role_name="分镜文案 Agent",
                enabled=True,
            ),
            TeamMemberResponse(
                member_id="m-prompt",
                persona_preset_id="preset-1",
                role_name="提示词 Agent",
                enabled=True,
            ),
        ],
        user_input="一份完整的抖音策划，包含首帧图和文案，但不仅限于上述内容的完整内容。",
    )

    assert fake_graph.astream_events_calls == 1
    assert fake_graph.ainvoke_calls == 2
    assert "分镜文案 Agent" in str(fake_graph.ainvoke_inputs[0])
    assert "提示词 Agent" in str(fake_graph.ainvoke_inputs[1])


@pytest.mark.asyncio
async def test_team_router_forces_all_members_for_complete_short_video_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-manager",
                persona_preset_id="preset-1",
                role_name="管理 Agent",
                enabled=True,
            ),
            TeamMemberResponse(
                member_id="m-copywriter",
                persona_preset_id="preset-1",
                role_name="分镜文案 Agent",
                enabled=True,
            ),
            TeamMemberResponse(
                member_id="m-prompt",
                persona_preset_id="preset-1",
                role_name="提示词 Agent",
                enabled=True,
            ),
        ],
        user_input="一份完整的抖音策划，包含首帧图和文案，但不仅限于上述内容的完整内容。",
    )
    assert fake_graph.astream_events_calls == 2
    assert fake_graph.ainvoke_calls == 3
    assert "管理 Agent" in str(fake_graph.ainvoke_inputs[0])
    assert "分镜文案 Agent" in str(fake_graph.ainvoke_inputs[1])
    assert "提示词 Agent" in str(fake_graph.ainvoke_inputs[2])


@pytest.mark.asyncio
async def test_team_router_allows_unrelated_team_completion_without_delegation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

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
        user_input="请先概括一下团队任务范围。",
    )
    assert fake_graph.astream_events_calls == 1


@pytest.mark.asyncio
async def test_team_member_without_model_override_uses_main_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

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
    assert get_model_calls[0]["streaming"] is False


@pytest.mark.asyncio
async def test_team_member_model_override_sets_subagent_model_and_profile_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
    from src.kernel.schemas.model import ModelConfig, ModelProfile

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
    monkeypatch.setattr(team_nodes, "ImageUrlToBase64Middleware", lambda: "image-b64")

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
    assert [call.get("streaming") for call in get_model_calls] == [False, False]


@pytest.mark.asyncio
async def test_multiple_team_members_use_their_own_model_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
    from src.kernel.schemas.model import ModelConfig

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

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

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
async def test_legacy_team_member_agent_id_does_not_break_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_deepagents_shims(monkeypatch)

    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)

    await _run_team_node_with_members(
        monkeypatch,
        team_nodes,
        fake_graph,
        [
            TeamMemberResponse(
                member_id="m-research",
                persona_preset_id="preset-1",
                role_name="Researcher",
                enabled=True,
            )
        ],
    )

    assert fake_graph.captured_create_kwargs is not None


def test_team_agent_runtime_no_longer_resolves_member_agent_modes() -> None:
    source = Path("plugins/system/agent_team/backend/runtime/nodes.py").read_text(encoding="utf-8")

    assert "resolve_team_member_agent_id" not in source
    assert "_build_member_agent_mode_sections" not in source


@pytest.mark.asyncio
async def test_team_member_model_access_rejects_missing_runtime_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
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

    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
    from plugins.system.agent_team.backend.runtime.context import TeamAgentContext

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
    monkeypatch.setattr(team_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

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
    from plugins.system.agent_team.backend.runtime.graph import TeamAgent

    assert TeamAgent._supports_sandbox is True
