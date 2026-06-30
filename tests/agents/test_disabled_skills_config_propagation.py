from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest


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
    monkeypatch.setattr(module, "SubagentActivityMiddleware", lambda **_kwargs: object())
    monkeypatch.setattr(module, "PromptCachingMiddleware", lambda: object())
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
        def __init__(self, *, deferred_manager, search_limit) -> None:
            captured_managers.append(deferred_manager)
            self.search_limit = search_limit

    monkeypatch.setattr(middleware_pkg, "ToolSearchMiddleware", _FakeToolSearchMiddleware)
    return captured_managers


def _context_with_internal_tool(tool) -> SimpleNamespace:
    async def get_tools():
        return [tool]

    return SimpleNamespace(
        user_id="user-1",
        skills=[],
        deferred_manager=None,
        get_tools=get_tools,
        filter_tools=lambda: [tool],
    )


def _context_without_tools(*, skills: list[dict] | None = None) -> SimpleNamespace:
    async def get_tools():
        return []

    return SimpleNamespace(
        user_id="user-1",
        skills=skills or [],
        deferred_manager=None,
        get_tools=get_tools,
        filter_tools=lambda: [],
    )


@pytest.mark.asyncio
async def test_fast_agent_node_propagates_disabled_skills_to_inner_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

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

    assert fast_nodes._test_get_model_calls[0]["streaming"] is False
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

    def backend_factory(_runtime):
        return backend_instance

    monkeypatch.setattr(
        fast_nodes,
        "create_persistent_backend_factory",
        lambda **_kwargs: backend_factory,
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
async def test_fast_agent_node_passes_internal_tools_when_mcp_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

    workflow_tool = SimpleNamespace(name="workflow_run")
    context = _context_with_internal_tool(workflow_tool)
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
    assert fake_graph.captured_create_kwargs["tools"] == [workflow_tool]


@pytest.mark.asyncio
async def test_fast_agent_subagent_middleware_retags_prompt_cache_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())
    monkeypatch.setattr(fast_nodes, "PromptCachingMiddleware", lambda: "prompt-cache")

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
    assert subagent_middleware[-1] == "prompt-cache"


@pytest.mark.asyncio
async def test_fast_agent_subagent_tool_search_uses_isolated_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())
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

    assert deferred_manager.fork_calls == ["subagent:general-purpose"]
    assert captured_managers[0] is deferred_manager.forked
    assert captured_managers[1] is deferred_manager


@pytest.mark.asyncio
async def test_fast_agent_node_returns_output_text_before_final_processor_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())
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
    monkeypatch.setattr(fast_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())
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
async def test_fast_agent_node_passes_existing_state_messages_to_concurrent_recommendations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    fake_graph.state_messages = ["history message"]
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())
    monkeypatch.setattr(fast_nodes.settings, "ENABLE_RECOMMEND_QUESTIONS", True)
    _FakeEventProcessor.next_output_text = "assistant answer"
    calls = []

    def fake_schedule_recommend_questions(presenter, user_input, output_text="", messages=None):
        calls.append((presenter, user_input, output_text, messages))

    import src.agents.core.recommendations as recommendations

    monkeypatch.setattr(
        recommendations,
        "schedule_recommend_questions",
        fake_schedule_recommend_questions,
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

    assert calls == [(presenter, "hello", "", ["history message"])]


@pytest.mark.asyncio
async def test_fast_agent_node_continues_when_recommendation_scheduling_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.fast_agent import nodes as fast_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, fast_nodes, fake_graph)
    monkeypatch.setattr(fast_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())
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

    assert search_nodes._test_get_model_calls[0]["streaming"] is False
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

    def backend_factory(_runtime):
        return backend_instance

    async def fake_create_backend_and_prompt(**_kwargs):
        return backend_factory, "system prompt", object(), None, None

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
async def test_search_agent_subagent_middleware_retags_prompt_cache_last(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.search_agent import nodes as search_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, search_nodes, fake_graph)
    monkeypatch.setattr(search_nodes, "PromptCachingMiddleware", lambda: "prompt-cache")

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
    assert subagent_middleware[-1] == "prompt-cache"


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

    assert deferred_manager.fork_calls == ["subagent:general-purpose"]
    assert captured_managers[0] is deferred_manager.forked
    assert captured_managers[1] is deferred_manager


@pytest.mark.asyncio
async def test_search_agent_node_passes_internal_tools_when_mcp_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.search_agent import nodes as search_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, search_nodes, fake_graph)

    async def fake_create_backend_and_prompt(**_kwargs):
        return object(), "system prompt", object(), None, None

    monkeypatch.setattr(search_nodes, "_create_backend_and_prompt", fake_create_backend_and_prompt)

    workflow_tool = SimpleNamespace(name="workflow_run")
    context = _context_with_internal_tool(workflow_tool)
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
    assert fake_graph.captured_create_kwargs["tools"] == [workflow_tool]


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
    monkeypatch.setattr(team_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

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

    context = _context_without_tools(
        skills=[
            {
                "name": "xiaohongshu-copy",
                "description": "Write Xiaohongshu-style copy.",
            },
            {
                "name": "unrelated-skill",
                "description": "Should not be injected for this role.",
            },
        ]
    )
    config = {
        "configurable": {
            "context": context,
            "presenter": object(),
            "base_url": "",
            "agent_options": {
                "_plugin_results": {
                    "workflow": {
                        "workflow_id": "wf-team",
                        "version_id": "wfv-team",
                        "run_id": "wfr-team",
                        "status": "succeeded",
                        "output": {"answer": 42, "trace": "runtime detail"},
                        "io_contract": {
                            "output_schema": {
                                "type": "object",
                                "required": ["answer", "summary"],
                                "properties": {
                                    "answer": {"type": "string"},
                                    "summary": {"type": "string"},
                                },
                            }
                        },
                        "output_contract": {
                            "valid": False,
                            "missing_required": ["summary"],
                            "type_mismatches": [
                                {"field": "answer", "expected": "string", "actual": "int"}
                            ],
                        },
                        "interface": {
                            "entry": {
                                "tool": "workflow_run",
                                "argument": "input",
                                "schema_tool": "workflow_get_schema",
                                "schema_field": "input_schema",
                            },
                            "exit": {
                                "field": "output",
                                "schema_tool": "workflow_get_schema",
                                "schema_field": "output_schema",
                            },
                            "debug": {"tool": "workflow_get_run", "events_field": "events"},
                        },
                        "next_action": {
                            "type": "use_output",
                            "field": "output",
                            "reason": "workflow_run_succeeded",
                        },
                        "error": None,
                    }
                }
            },
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
    section_middleware = next(mw for mw in subagent["middleware"] if hasattr(mw, "_sections"))
    sections = "\n\n".join(section_middleware._sections)
    assert "你是小红书风格文案写手，语气活泼可爱。" in sections
    assert "### Role Instructions" in sections
    assert "多用 emoji，保持小红书博主语气。" in sections
    assert "## Skills System" in sections
    assert "xiaohongshu-copy" in sections
    assert "unrelated-skill" not in sections
    assert "## Workflow Result" in sections
    assert "workflow_id: wf-team" in sections
    assert "run_id: wfr-team" in sections
    assert "output: 42" in sections
    assert "outputs: answer:string, summary:string" in sections
    assert "output_contract: invalid" in sections
    assert 'missing_required_outputs: ["summary"]' in sections
    assert '"actual": "int"' in sections
    assert (
        "interface: entry=workflow_run.input schema=workflow_get_schema.input_schema "
        "exit=output output_schema=workflow_get_schema.output_schema "
        "debug=workflow_get_run.events"
    ) in sections
    assert "next_action: use_output output reason=workflow_run_succeeded" in sections
    assert fake_graph.captured_inner_config is not None
    assert fake_graph.captured_inner_config["configurable"]["enabled_skills"] is None

    router_section_middleware = next(
        mw for mw in fake_graph.captured_create_kwargs["middleware"] if hasattr(mw, "_sections")
    )
    router_sections = "\n\n".join(router_section_middleware._sections)
    assert "## Persona" not in router_sections
    assert "## Skills System" not in router_sections
    assert "xiaohongshu-copy" not in router_sections
    assert "## Workflow Result" in router_sections
    assert "workflow_id: wf-team" in router_sections
    assert "outputs: answer:string, summary:string" in router_sections
    assert "output_contract: invalid" in router_sections
    assert "interface: entry=workflow_run.input schema=workflow_get_schema.input_schema" in router_sections
    assert "output_schema=workflow_get_schema.output_schema" in router_sections
    assert "next_action: use_output output reason=workflow_run_succeeded" in router_sections


def test_team_agent_workflow_result_prompt_section_prefers_nested_output_contract() -> None:
    from src.agents.team_agent import nodes as team_nodes

    section = team_nodes.workflow_result_prompt_section(
        {
            "_plugin_results": {
                "workflow": {
                    "workflow_id": "wf-team",
                    "version_id": "wfv-team",
                    "run_id": "wfr-team",
                    "status": "succeeded",
                    "output": {
                        "answer": "Generic answer",
                        "report": {"summary": "Nested team summary"},
                    },
                    "io_contract": {
                        "output_schema": {
                            "type": "object",
                            "required": ["report"],
                            "properties": {
                                "answer": {"type": "string"},
                                "report": {
                                    "type": "object",
                                    "required": ["summary"],
                                    "properties": {"summary": {"type": "string"}},
                                },
                            },
                        }
                    },
                    "output_contract": {"valid": True},
                    "interface": {
                        "entry": {
                            "tool": "workflow_run",
                            "argument": "input",
                            "schema_tool": "workflow_get_schema",
                            "schema_field": "input_schema",
                        },
                        "exit": {
                            "field": "output",
                            "schema_tool": "workflow_get_schema",
                            "schema_field": "output_schema",
                        },
                        "debug": {"tool": "workflow_get_run", "events_field": "events"},
                    },
                    "next_action": {
                        "type": "use_output",
                        "field": "output",
                        "reason": "workflow_run_succeeded",
                    },
                }
            }
        }
    )

    assert "## Workflow Result" in section
    assert "output: \"Nested team summary\"" in section
    assert "outputs: report.summary:string, answer:string" in section
    assert "output_contract: valid" in section
    assert (
        "interface: entry=workflow_run.input schema=workflow_get_schema.input_schema "
        "exit=output output_schema=workflow_get_schema.output_schema "
        "debug=workflow_get_run.events"
    ) in section
    assert "next_action: use_output output reason=workflow_run_succeeded" in section


@pytest.mark.asyncio
async def test_team_agent_node_passes_internal_tools_when_mcp_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.team_agent import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(team_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

    async def fake_resolve_runtime_team(**_kwargs):
        return None

    monkeypatch.setattr(team_nodes, "resolve_runtime_team", fake_resolve_runtime_team)

    workflow_tool = SimpleNamespace(name="workflow_run")
    context = _context_with_internal_tool(workflow_tool)
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
    assert fake_graph.captured_create_kwargs["tools"] == [workflow_tool]


@pytest.mark.asyncio
async def test_team_agent_node_adds_code_interpreter_middleware_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_event_processor()
    from src.agents.team_agent import nodes as team_nodes

    fake_graph = _FakeDeepAgent()
    _patch_common(monkeypatch, team_nodes, fake_graph)
    monkeypatch.setattr(team_nodes.settings, "ENABLE_SANDBOX", False)
    monkeypatch.setattr(team_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

    async def fake_resolve_runtime_team(**_kwargs):
        return None

    monkeypatch.setattr(team_nodes, "resolve_runtime_team", fake_resolve_runtime_team)

    code_middleware = object()
    monkeypatch.setattr(
        team_nodes,
        "create_code_interpreter_middleware",
        lambda agent_options: (
            [code_middleware] if agent_options.get("enable_code_interpreter") is True else []
        ),
    )

    async def get_tools():
        return []

    context = SimpleNamespace(
        user_id="user-1",
        skills=[],
        deferred_manager=None,
        get_tools=get_tools,
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
    monkeypatch.setattr(team_nodes, "create_persistent_backend_factory", lambda **_kwargs: object())

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

    context = _context_without_tools(
        skills=[{"name": "redbook-publish", "description": "Publish content to Xiaohongshu."}],
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
    section_middleware = next(mw for mw in subagent["middleware"] if hasattr(mw, "_sections"))
    sections = "\n\n".join(section_middleware._sections)
    assert "你是诗词卡片设计师。" in sections
    assert "## Skills System" in sections
    assert "redbook-publish" in sections

    router_section_middleware = next(
        mw for mw in fake_graph.captured_create_kwargs["middleware"] if hasattr(mw, "_sections")
    )
    router_sections = "\n\n".join(router_section_middleware._sections)
    assert "redbook-publish" not in router_sections
