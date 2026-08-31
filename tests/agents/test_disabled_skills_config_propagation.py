from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.agent.middleware import SectionPromptMiddleware


def _section_prompt(middleware: list[object]) -> str:
    return next(mw._prompt for mw in middleware if isinstance(mw, SectionPromptMiddleware))


class _FakeDeepAgent:
    def __init__(self) -> None:
        self.captured_create_kwargs = None
        self.captured_inner_config = None
        self.aget_state_calls = 0
        self.state_messages = []

    def with_config(self, _config):
        return self

    async def astream_events(self, _initial_state, config, version="v2"):
        self.captured_inner_config = config
        if False:
            yield version

    async def aget_state(self, _config):
        self.aget_state_calls += 1
        return SimpleNamespace(values={"messages": self.state_messages})


class _FakeEventProcessor:
    next_output_text = ""

    def __init__(self, *_args, **_kwargs) -> None:
        self.output_text = self.next_output_text

    async def process_event(self, _event) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def finalize(self) -> None:
        self.output_text = ""
        return None

    def clear(self) -> None:
        return None


class _FakeDeferredManager:
    def __init__(self) -> None:
        self.fork_calls: list[str] = []
        self.forked = SimpleNamespace(label="subagent-deferred-manager")
        self.discovered_count = 0
        self.discovered_names: list[str] = []

    def fork_for_scope(self, scope: str):
        self.fork_calls.append(scope)
        return self.forked


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
    monkeypatch.setattr(module.settings, "ENABLE_MCP", False)
    monkeypatch.setattr(module.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(module.settings, "ENABLE_SKILLS", False)
    monkeypatch.setattr(module.settings, "ENABLE_RECOMMEND_QUESTIONS", False)


def _reset_fake_event_processor() -> None:
    _FakeEventProcessor.next_output_text = ""


def _patch_tool_search_middleware(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    from src.infra.agent import middleware as middleware_pkg

    captured_managers: list[object] = []

    class _FakeToolSearchMiddleware:
        def __init__(self, *, deferred_manager, search_limit, user_id=None) -> None:
            captured_managers.append(deferred_manager)
            self.search_limit = search_limit
            self.user_id = user_id

    monkeypatch.setattr(middleware_pkg, "ToolSearchMiddleware", _FakeToolSearchMiddleware)
    return captured_managers


@pytest.mark.asyncio
async def test_fast_agent_node_propagates_disabled_skills_to_inner_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend", lambda **_kwargs: object())

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    presenter = object()
    config = {
        "configurable": {
            "context": context,
            "presenter": presenter,
            "disabled_skills": ["hidden-skill"],
            "base_url": "",
            "agent_options": {},
        }
    }

    await fast_nodes.fast_agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_inner_config is not None
    assert fake_graph.captured_inner_config["configurable"]["disabled_skills"] == ["hidden-skill"]


@pytest.mark.asyncio
async def test_fast_agent_node_passes_backend_instance_to_deepagents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)

    backend_instance = object()

    monkeypatch.setattr(
        fast_nodes,
        "create_persistent_backend",
        lambda **_kwargs: backend_instance,
    )

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    await fast_nodes.fast_agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    assert fake_graph.captured_create_kwargs["backend"] is backend_instance
    assert fake_graph.captured_inner_config is not None
    assert fake_graph.captured_inner_config["configurable"]["backend"] is backend_instance


@pytest.mark.asyncio
async def test_fast_agent_subagent_keeps_functional_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend", lambda **_kwargs: object())
    binary = object()
    artifact = object()
    activity = object()
    monkeypatch.setattr(fast_nodes, "ToolResultBinaryMiddleware", lambda **_kwargs: binary)
    monkeypatch.setattr(fast_nodes, "ArtifactDeliveryMiddleware", lambda **_kwargs: artifact)
    monkeypatch.setattr(fast_nodes, "SubagentActivityMiddleware", lambda **_kwargs: activity)

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    await fast_nodes.fast_agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    subagent_middleware = fake_graph.captured_create_kwargs["subagents"][0]["middleware"]
    assert subagent_middleware[:3] == [binary, artifact, activity]


@pytest.mark.asyncio
async def test_fast_agent_subagent_tool_search_uses_isolated_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend", lambda **_kwargs: object())
    captured_managers = _patch_tool_search_middleware(monkeypatch)

    deferred_manager = _FakeDeferredManager()
    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=deferred_manager)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    await fast_nodes.fast_agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert "subagent:general-purpose" in deferred_manager.fork_calls
    assert captured_managers[0] is deferred_manager.forked
    assert captured_managers[-1] is deferred_manager
    assert [tool.name for tool in fake_graph.captured_create_kwargs["tools"]].count(
        "search_tools"
    ) == 1


@pytest.mark.asyncio
async def test_fast_agent_node_returns_output_text_before_final_processor_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend", lambda **_kwargs: object())
    _FakeEventProcessor.next_output_text = "vision answer"

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    result = await fast_nodes.fast_agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert result["output"] == "vision answer"


@pytest.mark.asyncio
async def test_fast_agent_node_reads_existing_state_messages_for_recommendations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    fake_graph.state_messages = ["history message"]
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend", lambda **_kwargs: object())
    monkeypatch.setattr(fast_nodes.settings, "ENABLE_RECOMMEND_QUESTIONS", True)

    import src.agents.core.recommendations as recommendations

    monkeypatch.setattr(
        recommendations,
        "schedule_recommend_questions",
        lambda *_args, **_kwargs: None,
    )

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    result = await fast_nodes.fast_agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )
    await asyncio.sleep(0)

    assert fake_graph.aget_state_calls == 1
    assert result == {"output": ""}


@pytest.mark.asyncio
async def test_fast_agent_node_schedules_recommendations_with_final_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    fake_graph.state_messages = ["history message"]
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend", lambda **_kwargs: object())
    monkeypatch.setattr(fast_nodes.settings, "ENABLE_RECOMMEND_QUESTIONS", True)
    _FakeEventProcessor.next_output_text = "assistant answer"
    calls = []

    def fake_schedule_recommend_questions_from_state(
        presenter,
        user_input,
        output_text,
        inner_graph,
        inner_config,
        response_language=None,
    ):
        calls.append((presenter, user_input, output_text, inner_graph, inner_config))

    import src.agents.core.recommendations as recommendations

    monkeypatch.setattr(
        recommendations,
        "schedule_recommend_questions_from_state",
        fake_schedule_recommend_questions_from_state,
    )

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    presenter = object()
    config = {
        "configurable": {
            "context": context,
            "presenter": presenter,
            "base_url": "",
            "agent_options": {},
            "recommendation_input": "hello",
        }
    }

    await fast_nodes.fast_agent_node(
        {
            "input": "[User message sent at: 2026-06-06 18:42:00 +00:00 UTC] hello",
            "session_id": "session-1",
            "attachments": [],
        },
        config,
    )
    await asyncio.sleep(0)

    assert len(calls) == 1
    assert calls[0][0:4] == (presenter, "hello", "assistant answer", fake_graph)
    assert calls[0][4] == fake_graph.captured_inner_config


@pytest.mark.asyncio
async def test_fast_agent_node_continues_when_recommendation_scheduling_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend", lambda **_kwargs: object())
    monkeypatch.setattr(fast_nodes.settings, "ENABLE_RECOMMEND_QUESTIONS", True)
    _FakeEventProcessor.next_output_text = "assistant answer"

    def fail_schedule(*_args, **_kwargs):
        raise RuntimeError("recommendation unavailable")

    import src.agents.core.recommendations as recommendations

    monkeypatch.setattr(recommendations, "schedule_recommend_questions", fail_schedule)

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    result = await fast_nodes.fast_agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )
    await asyncio.sleep(0)

    assert result["output"] == "assistant answer"


@pytest.mark.asyncio
async def test_search_agent_node_propagates_disabled_skills_to_inner_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.search_agent import nodes as search_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, search_nodes, fake_graph)

    async def fake_create_backend_and_prompt(**_kwargs):
        return object(), "system prompt", object(), None, None

    monkeypatch.setattr(search_nodes, "_create_backend_and_prompt", fake_create_backend_and_prompt)

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    presenter = object()
    config = {
        "configurable": {
            "context": context,
            "presenter": presenter,
            "disabled_skills": ["hidden-skill"],
            "base_url": "",
            "agent_options": {},
        }
    }

    await search_nodes.agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_inner_config is not None
    assert fake_graph.captured_inner_config["configurable"]["disabled_skills"] == ["hidden-skill"]


@pytest.mark.asyncio
async def test_search_agent_node_passes_backend_instance_to_deepagents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.search_agent import nodes as search_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, search_nodes, fake_graph)

    backend_instance = object()

    async def fake_create_backend_and_prompt(**_kwargs):
        return backend_instance, "system prompt", object(), None, None

    monkeypatch.setattr(search_nodes, "_create_backend_and_prompt", fake_create_backend_and_prompt)

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    await search_nodes.agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    assert fake_graph.captured_create_kwargs["backend"] is backend_instance
    assert fake_graph.captured_inner_config is not None
    assert fake_graph.captured_inner_config["configurable"]["backend"] is backend_instance


@pytest.mark.asyncio
async def test_search_agent_subagent_keeps_functional_middleware(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.search_agent import nodes as search_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, search_nodes, fake_graph)
    binary = object()
    artifact = object()
    activity = object()
    monkeypatch.setattr(search_nodes, "ToolResultBinaryMiddleware", lambda **_kwargs: binary)
    monkeypatch.setattr(search_nodes, "ArtifactDeliveryMiddleware", lambda **_kwargs: artifact)
    monkeypatch.setattr(search_nodes, "SubagentActivityMiddleware", lambda **_kwargs: activity)

    async def fake_create_backend_and_prompt(**_kwargs):
        return object(), "system prompt", object(), None, None

    monkeypatch.setattr(search_nodes, "_create_backend_and_prompt", fake_create_backend_and_prompt)

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    await search_nodes.agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    subagent_middleware = fake_graph.captured_create_kwargs["subagents"][0]["middleware"]
    assert subagent_middleware[:3] == [binary, artifact, activity]


@pytest.mark.asyncio
async def test_search_agent_subagent_tool_search_uses_isolated_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.search_agent import nodes as search_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, search_nodes, fake_graph)
    captured_managers = _patch_tool_search_middleware(monkeypatch)

    async def fake_create_backend_and_prompt(**_kwargs):
        return object(), "system prompt", object(), None, None

    monkeypatch.setattr(search_nodes, "_create_backend_and_prompt", fake_create_backend_and_prompt)

    deferred_manager = _FakeDeferredManager()
    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=deferred_manager)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    await search_nodes.agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert "subagent:general-purpose" in deferred_manager.fork_calls
    assert captured_managers[0] is deferred_manager.forked
    assert captured_managers[-1] is deferred_manager


@pytest.mark.asyncio
async def test_search_agent_node_returns_output_text_before_final_processor_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.search_agent import nodes as search_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, search_nodes, fake_graph)
    _FakeEventProcessor.next_output_text = "vision answer"

    async def fake_create_backend_and_prompt(**_kwargs):
        return object(), "system prompt", object(), None, None

    monkeypatch.setattr(search_nodes, "_create_backend_and_prompt", fake_create_backend_and_prompt)

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    result = await search_nodes.agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )

    assert result["output"] == "vision answer"


@pytest.mark.asyncio
async def test_search_agent_node_reads_existing_state_messages_for_recommendations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.search_agent import nodes as search_nodes

    fake_graph = _FakeDeepAgent()
    fake_graph.state_messages = ["history message"]
    _patch_common(monkeypatch, search_nodes, fake_graph)
    monkeypatch.setattr(search_nodes.settings, "ENABLE_RECOMMEND_QUESTIONS", True)

    import src.agents.core.recommendations as recommendations

    monkeypatch.setattr(
        recommendations,
        "schedule_recommend_questions",
        lambda *_args, **_kwargs: None,
    )

    async def fake_create_backend_and_prompt(**_kwargs):
        return object(), "system prompt", object(), None, None

    monkeypatch.setattr(search_nodes, "_create_backend_and_prompt", fake_create_backend_and_prompt)

    context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
        }
    }

    result = await search_nodes.agent_node(
        {"input": "hello", "session_id": "session-1", "attachments": []},
        config,
    )
    await asyncio.sleep(0)

    assert fake_graph.aget_state_calls == 1
    assert result == {"output": ""}


@pytest.mark.asyncio
async def test_team_role_subagent_prompt_includes_role_instructions_and_skills(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.team import TeamMemberResponse, TeamResponse

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SKILLS", True)
    monkeypatch.setattr(team_nodes, "create_persistent_backend", lambda **_kwargs: object())

    team = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="Creative Team",
        members=[
            TeamMemberResponse(
                member_id="m-writer",
                persona_preset_id="preset-writer",
                role_name="小红书风格文案写手",
                role_instructions="多用 emoji，保持小红书博主语气。",
                enabled=True,
            )
        ],
    )

    async def fake_resolve_runtime_team(**_kwargs):
        return team

    monkeypatch.setattr(team_nodes, "resolve_runtime_team", fake_resolve_runtime_team)

    class _PresetManager:
        async def use_preset(self, *_args, **_kwargs):
            return SimpleNamespace(
                system_prompt="你是小红书风格文案写手，语气活泼可爱。",
                skill_names=["xiaohongshu-copy"],
            )

    import src.infra.persona_preset.manager as persona_manager

    monkeypatch.setattr(
        persona_manager,
        "get_persona_preset_manager",
        lambda: _PresetManager(),
    )

    from src.infra.skill.skill_search_tool import SkillSearchTool

    context_skills = [
        {
            "name": "xiaohongshu-copy",
            "description": "Write Xiaohongshu-style copy.",
        },
        {
            "name": "unrelated-skill",
            "description": "Should not be injected for this role.",
        },
    ]
    context = SimpleNamespace(
        user_id="user-1",
        skills=context_skills,
        deferred_manager=None,
        get_tools=lambda: [],
        filter_tools=lambda: [SkillSearchTool(context_skills)],
    )
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {},
            "team_id": "team-1",
            "enabled_skills": ["unrelated-skill"],
        }
    }

    await team_nodes.team_router_node(
        {"input": "打个招呼", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    subagent = fake_graph.captured_create_kwargs["subagents"][0]
    assert subagent["system_prompt"] == team_nodes.SUBAGENT_PROMPT
    sections = _section_prompt(subagent["middleware"])
    assert "你是小红书风格文案写手，语气活泼可爱。" in sections
    assert "### Role Instructions" in sections
    assert "多用 emoji，保持小红书博主语气。" in sections
    assert "## Skills System" not in sections
    role_search = next(tool for tool in subagent["tools"] if tool.name == "search_skills")
    # Codex-style layering: the Skill inventory rides on the search_skills
    # tool description instead of the system prompt.
    assert "## Skills System" in role_search.description
    assert "xiaohongshu-copy" in role_search.description
    assert "unrelated-skill" not in role_search.description
    assert "Name: xiaohongshu-copy" in role_search._run("xiaohongshu")
    assert role_search._run("unrelated-skill") == "No Skills matched that query."
    assert fake_graph.captured_inner_config is not None
    assert fake_graph.captured_inner_config["configurable"]["enabled_skills"] is None

    router_sections = _section_prompt(fake_graph.captured_create_kwargs["middleware"])
    assert "## Persona" not in router_sections
    assert "## Skills System" not in router_sections
    assert "xiaohongshu-copy" not in router_sections


@pytest.mark.asyncio
async def test_team_agent_node_adds_code_interpreter_middleware_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.team_agent import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(team_nodes, "create_persistent_backend", lambda **_kwargs: object())

    async def fake_resolve_runtime_team(**_kwargs):
        return None

    monkeypatch.setattr(team_nodes, "resolve_runtime_team", fake_resolve_runtime_team)

    code_middleware = object()
    captured_sandbox_active = []
    monkeypatch.setattr(
        team_nodes,
        "create_code_interpreter_middleware",
        lambda agent_options, *, sandbox_active=False: (
            captured_sandbox_active.append(sandbox_active)
            or ([code_middleware] if agent_options.get("enable_code_interpreter") is True else [])
        ),
    )

    context = SimpleNamespace(
        user_id="user-1",
        skills=[],
        deferred_manager=None,
        get_tools=lambda: [],
        filter_tools=lambda: [],
    )
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {"enable_code_interpreter": True},
        }
    }

    await team_nodes.team_router_node(
        {"input": "run code", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    assert code_middleware in fake_graph.captured_create_kwargs["middleware"]
    assert captured_sandbox_active == [False]


@pytest.mark.asyncio
async def test_team_role_subagent_inherits_global_skills_when_role_skills_are_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.team_agent import nodes as team_nodes
    from src.kernel.schemas.team import TeamMemberResponse, TeamResponse

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SKILLS", True)
    monkeypatch.setattr(team_nodes, "create_persistent_backend", lambda **_kwargs: object())

    team = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="Creative Team",
        members=[
            TeamMemberResponse(
                member_id="m-designer",
                persona_preset_id="preset-designer",
                role_name="诗词卡片设计师",
                enabled=True,
            )
        ],
    )

    async def fake_resolve_runtime_team(**_kwargs):
        return team

    monkeypatch.setattr(team_nodes, "resolve_runtime_team", fake_resolve_runtime_team)

    class _PresetManager:
        async def use_preset(self, *_args, **_kwargs):
            return SimpleNamespace(system_prompt="你是诗词卡片设计师。", skill_names=[])

    import src.infra.persona_preset.manager as persona_manager

    monkeypatch.setattr(persona_manager, "get_persona_preset_manager", lambda: _PresetManager())

    context = SimpleNamespace(
        user_id="user-1",
        skills=[{"name": "redbook-publish", "description": "Publish content to Xiaohongshu."}],
        deferred_manager=None,
        get_tools=lambda: [],
        filter_tools=lambda: [],
    )
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
        {"input": "设计一张诗词卡片", "session_id": "session-1", "attachments": []},
        config,
    )

    assert fake_graph.captured_create_kwargs is not None
    subagent = fake_graph.captured_create_kwargs["subagents"][0]
    sections = _section_prompt(subagent["middleware"])
    assert "你是诗词卡片设计师。" in sections
    assert "## Skills System" not in sections
    subagent_tools = subagent.get("tools") or []
    if subagent_tools:
        role_search = next(tool for tool in subagent_tools if tool.name == "search_skills")
        assert "## Skills System" in role_search.description
        assert "redbook-publish" in role_search.description

    router_sections = _section_prompt(fake_graph.captured_create_kwargs["middleware"])
    assert "redbook-publish" not in router_sections


@pytest.mark.asyncio
async def test_fast_agent_node_language_section_bytes_stable_across_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """语言段是 agent_options 的纯函数：连续两轮字节一致，前缀缓存不失效。"""
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    async def run_turn(agent_options: dict) -> str:
        fake_graph = _FakeDeepAgent()
        _patch_common(monkeypatch, fast_nodes, fake_graph)
        context = SimpleNamespace(user_id="user-1", skills=[], deferred_manager=None)
        await fast_nodes.fast_agent_node(
            {"input": "hello", "session_id": "session-1", "attachments": []},
            {
                "configurable": {
                    "context": context,
                    "presenter": object(),
                    "base_url": "",
                    "agent_options": dict(agent_options),
                }
            },
        )
        return _section_prompt(fake_graph.captured_create_kwargs["middleware"])

    first_turn = await run_turn({"response_language": "zh"})
    second_turn = await run_turn({"response_language": "zh"})

    assert first_turn == second_turn
    assert "Simplified Chinese" in first_turn

    # 未带语言的请求：段落与历史字节一致，零缓存影响
    without_language = await run_turn({})
    assert "Response Language" not in without_language
    assert without_language == first_turn.replace(
        "\n\n### Response Language\n- Respond in Simplified Chinese unless the user"
        " explicitly asks for another language.\n- Keep code, commands, error messages,"
        " file paths, and technical identifiers unchanged.",
        "",
    )
