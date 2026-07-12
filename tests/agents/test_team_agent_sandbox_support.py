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


def test_team_prompt_cleaning_removes_corrupted_lines() -> None:
    from plugins.system.agent_team.backend.runtime.prompt import clean_team_prompt_text

    cleaned = clean_team_prompt_text(
        "完整素材包任务禁止在只完成需求梳理后结束。\n"
        "????????????????????????????????\n"
        "每次成员返回后 router 必须调用下一个指定成员。\n"
        "坏行��继续坏\n"
    )

    assert "完整素材包任务禁止在只完成需求梳理后结束" in cleaned
    assert "必须调用下一个指定成员" in cleaned
    assert "????????" not in cleaned
    assert "��" not in cleaned


def test_full_asset_stage_detection_does_not_overcount_broad_storyboard_task() -> None:
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

    event = {
        "event": "on_tool_start",
        "name": "task",
        "data": {
            "input": {
                "subagent_type": "team-copywriter-agent",
                "task": (
                    "Task type: MULTI_STAGE\n"
                    "Target member: 宣传文案与分镜片段生成 Agent\n"
                    "输出宣传文案、分镜、Scene 编号、画面目标。\n"
                    "上下文提到后续还会生成 Image Prompt EN、Negative Prompt EN、"
                    "Image-to-Video Prompt EN、image_generate、reveal_project 和下载包。"
                ),
            }
        },
    }

    assert team_nodes._collect_full_asset_package_stages_from_event(event) == {"storyboard"}


def test_full_asset_pipeline_prefers_prompt_engineer_member() -> None:
    from plugins.system.agent_team.backend.domain.schemas import TeamMemberResponse, TeamResponse
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes

    team = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="Asset Team",
        members=[
            TeamMemberResponse(
                member_id="manager",
                persona_preset_id="preset-1",
                role_name="片段级首帧图工作流管理 Agent",
                role_tags=["workflow", "agent-manager", "packaging"],
                enabled=True,
            ),
            TeamMemberResponse(
                member_id="copywriter",
                persona_preset_id="preset-1",
                role_name="宣传文案与分镜片段生成 Agent",
                role_tags=["copywriting", "storyboard", "short-video"],
                role_instructions="可接收上下文里的提示词交付要求，但本角色只写分镜文案。",
                enabled=True,
            ),
            TeamMemberResponse(
                member_id="prompt_engineer",
                persona_preset_id="preset-1",
                role_name="片段级首帧图与图生视频提示词生成 Agent",
                role_tags=["prompt", "first-frame", "image-to-video"],
                enabled=True,
            ),
        ],
    )

    pipeline = team_nodes._build_full_asset_package_pipeline(team)

    assert pipeline[0]["member"].member_id == "manager"
    assert pipeline[1]["member"].member_id == "copywriter"
    assert pipeline[2]["member"].member_id == "prompt_engineer"
    assert pipeline[3]["member"].member_id == "manager"


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
    assert fake_graph.astream_events_calls == 6
    assert fake_graph.ainvoke_calls == 0
    assert "Team router forced full asset package pipeline" in str(fake_graph.initial_states[2])
    assert "需求梳理" in str(fake_graph.initial_states[2])
    assert "Tool policy: NO_TOOLS" in str(fake_graph.initial_states[2])
    assert "Image Prompt EN" in str(fake_graph.initial_states[4])
    assert "image_generate" in str(fake_graph.initial_states[5])
    assert "reveal_project" in str(fake_graph.initial_states[5])


@pytest.mark.asyncio
async def test_forced_team_delegation_streams_tool_events_with_member_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugins.system.agent_team.backend.domain.schemas import (
        TeamMemberResponse,
        TeamResponse,
    )
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
    from plugins.system.agent_team.backend.runtime.context import TeamAgentContext

    member = TeamMemberResponse(
        member_id="m-tool",
        persona_preset_id="preset-1",
        role_name="Tool Agent",
        enabled=True,
    )
    team = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="Tool Team",
        members=[member],
    )
    subagent_type = team_nodes.build_team_member_subagent_type(member)
    fake_graph = _FakeDeepAgent()
    fake_graph.events = [
        {
            "event": "on_chat_model_stream",
            "name": "chat_model",
            "run_id": "chat-run-1",
            "metadata": {"langgraph_checkpoint_ns": "agent:inner"},
            "data": {"chunk": SimpleNamespace(content="member streamed detail", id="chunk-1")},
        },
        {
            "event": "on_tool_start",
            "name": "mcp_lookup",
            "run_id": "tool-run-1",
            "metadata": {"langgraph_checkpoint_ns": "agent:inner"},
            "data": {"input": {"query": "野自在"}},
        },
        {
            "event": "on_tool_end",
            "name": "mcp_lookup",
            "run_id": "tool-run-1",
            "metadata": {"langgraph_checkpoint_ns": "agent:inner"},
            "data": {"output": "normal tool result"},
        },
    ]
    fake_graph.state_messages = [SimpleNamespace(content="member final")]

    monkeypatch.setattr(team_nodes, "create_deep_agent", lambda **_kwargs: fake_graph)

    class _Presenter:
        trace_id = "trace-1"

        async def emit(self, _event):
            return None

        def present_agent_call(self, **kwargs):
            return {"event_type": "agent:call", "data": kwargs}

        def present_agent_result(self, **kwargs):
            return {"event_type": "agent:result", "data": kwargs}

    class _Processor:
        def __init__(self) -> None:
            self.checkpoint_to_agent = {}
            self._agent_context_cache = {}
            self.processed = []
            self.output_text = ""

        async def process_event(self, event):
            self.processed.append(event)

        async def flush(self):
            return None

        def _append_output_text(self, text):
            self.output_text += text

    processor = _Processor()

    count = await team_nodes._run_forced_team_delegation(
        team=team,
        user_input="一份完整素材包",
        reason="full_asset_package",
        custom_subagents=[
            {
                "name": subagent_type,
                "model": object(),
                "system_prompt": "You are a tool member.",
                "middleware": [],
            }
        ],
        llm=object(),
        backend=object(),
        filtered_tools=[],
        inner_checkpointer=object(),
        store=object(),
        context=TeamAgentContext(session_id="session-1", user_id="user-1"),
        presenter=_Presenter(),
        event_processor=processor,
        subagent_display_names={subagent_type: "Tool Agent"},
        subagent_avatars={},
        configurable={"session_id": "session-1"},
        attachments=[],
        config={},
        delegated_subagent_names=set(),
    )

    assert count == 5
    assert fake_graph.astream_events_calls == 4
    assert fake_graph.ainvoke_calls == 0
    member_tool_events = [
        event for event in processor.processed if event.get("name") == "mcp_lookup"
    ]
    member_text_events = [
        event for event in processor.processed if event.get("event") == "on_chat_model_stream"
    ]
    assert len(member_tool_events) == 8
    assert member_text_events == []
    assert "member streamed detail" not in processor.output_text
    assert "完整素材包兜底交付失败" in processor.output_text
    assert "Reveal result" not in processor.output_text
    checkpoint_roots = list(processor.checkpoint_to_agent)
    assert len(checkpoint_roots) == 4
    assert all(
        processor.checkpoint_to_agent[root][0].startswith(f"forced_{subagent_type}_")
        for root in checkpoint_roots
    )
    assert all(
        any(
            event["metadata"]["langgraph_checkpoint_ns"].startswith(f"{root}|")
            for event in member_tool_events
        )
        for root in checkpoint_roots
    )


@pytest.mark.asyncio
async def test_forced_team_delegation_preserves_existing_asset_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugins.system.agent_team.backend.domain.schemas import (
        TeamMemberResponse,
        TeamResponse,
    )
    from plugins.system.agent_team.backend.runtime import nodes as team_nodes
    from plugins.system.agent_team.backend.runtime.asset_delivery import AssetDeliveryEvidence
    from plugins.system.agent_team.backend.runtime.context import TeamAgentContext

    member = TeamMemberResponse(
        member_id="m-delivery",
        persona_preset_id="preset-1",
        role_name="Delivery Agent",
        enabled=True,
    )
    team = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="Delivery Team",
        members=[member],
    )
    subagent_type = team_nodes.build_team_member_subagent_type(member)
    fake_graph = _FakeDeepAgent()
    fake_graph.events = [
        {
            "event": "on_tool_end",
            "name": "image_generate",
            "data": {"output": '{"success":true,"images":[{"url":"/image.png"}]}'},
        },
        {
            "event": "on_tool_end",
            "name": "reveal_project",
            "data": {
                "output": {
                    "type": "project_reveal",
                    "files": {
                        "/scenes/scene_01/first_frame.png": {},
                        "/asset_package.zip": {},
                    },
                }
            },
        },
    ]
    fake_graph.state_messages = [SimpleNamespace(content="member final")]
    monkeypatch.setattr(team_nodes, "create_deep_agent", lambda **_kwargs: fake_graph)

    async def fail_if_fallback_runs(**_kwargs):
        raise AssertionError("deterministic fallback must not replace an existing delivery")

    monkeypatch.setattr(
        team_nodes,
        "_create_and_reveal_full_asset_package_fallback",
        fail_if_fallback_runs,
    )

    class _Presenter:
        trace_id = "trace-1"

        async def emit(self, _event):
            return None

        async def emit_text(self, _text):
            return None

        def present_agent_call(self, **kwargs):
            return {"event_type": "agent:call", "data": kwargs}

        def present_agent_result(self, **kwargs):
            return {"event_type": "agent:result", "data": kwargs}

    class _Processor:
        def __init__(self) -> None:
            self.checkpoint_to_agent = {}
            self._agent_context_cache = {}
            self.output_text = ""

        async def process_event(self, _event):
            return None

        async def flush(self):
            return None

        def _append_output_text(self, text):
            self.output_text += text

    processor = _Processor()
    evidence = AssetDeliveryEvidence()
    count = await team_nodes._run_forced_team_delegation(
        team=team,
        user_input="一份完整素材包",
        reason="full_asset_package",
        custom_subagents=[{"name": subagent_type, "model": object(), "middleware": []}],
        llm=object(),
        backend=object(),
        filtered_tools=[],
        inner_checkpointer=object(),
        store=object(),
        context=TeamAgentContext(session_id="session-1", user_id="user-1"),
        presenter=_Presenter(),
        event_processor=processor,
        subagent_display_names={subagent_type: "Delivery Agent"},
        subagent_avatars={},
        configurable={"session_id": "session-1"},
        attachments=[],
        config={},
        delegated_subagent_names=set(),
        delivery_evidence=evidence,
    )

    assert count == 5
    assert evidence.complete is True
    assert "完整交付" in processor.output_text


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

    assert fake_graph.astream_events_calls == 5
    assert "必须先调用 `task` 工具" in str(fake_graph.initial_states[1])
    assert "完整素材包流程" in str(fake_graph.initial_states[1])
    assert "需求梳理" in str(fake_graph.initial_states[2])
    assert "CREATE_FILES" in str(fake_graph.initial_states[4])


@pytest.mark.asyncio
async def test_team_router_forces_full_asset_package_stages_after_generic_task_delegation(
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
    assert fake_graph.astream_events_calls == 4
    assert fake_graph.ainvoke_calls == 0
    assert "需求梳理" in str(fake_graph.initial_states[1])
    assert "Image Prompt EN" in str(fake_graph.initial_states[2])
    assert "CREATE_FILES" in str(fake_graph.initial_states[3])


@pytest.mark.asyncio
async def test_team_router_does_not_force_when_full_asset_stages_are_delegated(
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
            "data": {
                "input": {
                    "subagent_type": "team-m-manager-agent",
                    "task": "需求梳理；素材包交付清单；可用素材；总时长",
                }
            },
        },
        {
            "event": "on_tool_start",
            "name": "task",
            "data": {
                "input": {
                    "subagent_type": "team-m-copywriter-agent",
                    "task": "宣传文案；分镜；Scene 编号；画面目标",
                }
            },
        },
        {
            "event": "on_tool_start",
            "name": "task",
            "data": {
                "input": {
                    "subagent_type": "team-m-prompt-agent",
                    "task": "Image Prompt EN；Negative Prompt EN；Image-to-Video Prompt EN；图生视频提示词",
                }
            },
        },
        {
            "event": "on_tool_start",
            "name": "task",
            "data": {
                "input": {
                    "subagent_type": "team-m-manager-agent",
                    "task": "FILE_ARTIFACT；CREATE_FILES；image_generate；reveal_project；下载包；scene_01",
                }
            },
        },
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
        user_input="一份完整的抖音策划，包含首帧图和素材包下载交付。",
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

    assert fake_graph.astream_events_calls == 5
    assert fake_graph.ainvoke_calls == 0
    assert "管理 Agent" in str(fake_graph.initial_states[1])
    assert "需求梳理" in str(fake_graph.initial_states[1])
    assert "分镜文案 Agent" in str(fake_graph.initial_states[2])
    assert "提示词 Agent" in str(fake_graph.initial_states[3])
    assert "管理 Agent" in str(fake_graph.initial_states[4])
    assert "CREATE_FILES" in str(fake_graph.initial_states[4])


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
    assert fake_graph.astream_events_calls == 6
    assert fake_graph.ainvoke_calls == 0
    assert "管理 Agent" in str(fake_graph.initial_states[2])
    assert "分镜文案 Agent" in str(fake_graph.initial_states[3])
    assert "提示词 Agent" in str(fake_graph.initial_states[4])
    assert "管理 Agent" in str(fake_graph.initial_states[5])
    assert "CREATE_FILES" in str(fake_graph.initial_states[5])


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
