from __future__ import annotations

import pytest

from src.agents.core.persona import build_persona_prompt_section
from src.agents.search_agent.context import SearchAgentContext
from src.api.routes.chat import build_conversation_config, resolve_persona_request
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.persona_preset import PersonaPresetSnapshot
from src.kernel.schemas.user import TokenPayload


def test_conversation_config_persists_persona_snapshot_and_enabled_skills() -> None:
    snapshot = PersonaPresetSnapshot(
        preset_id="preset-1",
        name="Planner",
        system_prompt="Plan first.",
        skill_names=["planning"],
        missing_skill_names=["unknown"],
        version=4,
    )
    request = AgentRequest(
        message="hello",
        persona_preset_id="preset-1",
        persona_snapshot=snapshot,
        enabled_skills=["planning"],
    )

    config = build_conversation_config(
        run_id="run-1",
        agent_id="search",
        request=request,
        language="zh",
    )

    assert config["persona_preset_id"] == "preset-1"
    assert config["persona_preset_name"] == "Planner"
    assert config["persona_snapshot"] == snapshot.model_dump()
    assert config["enabled_skills"] == ["planning"]


def test_conversation_config_ignores_persona_snapshot_without_preset_id() -> None:
    snapshot = PersonaPresetSnapshot(
        preset_id="preset-1",
        name="Planner",
        system_prompt="Plan first.",
        skill_names=["planning"],
        missing_skill_names=[],
        version=4,
    )
    request = AgentRequest(
        message="hello",
        persona_snapshot=snapshot,
        persona_system_prompt="inject me",
    )

    config = build_conversation_config(
        run_id="run-1",
        agent_id="search",
        request=request,
        language="zh",
    )

    assert "persona_preset_id" not in config
    assert "persona_preset_name" not in config
    assert "persona_snapshot" not in config


@pytest.mark.asyncio
async def test_resolve_persona_request_drops_client_persona_fields_without_preset_id() -> None:
    request = AgentRequest(
        message="hello",
        enabled_skills=["custom"],
        persona_snapshot=PersonaPresetSnapshot(
            preset_id="preset-1",
            name="Planner",
            system_prompt="Plan first.",
            skill_names=["planning"],
            missing_skill_names=[],
            version=1,
        ),
        persona_system_prompt="inject me",
    )
    user = TokenPayload(sub="user-1", username="tester", permissions=["chat:write"])

    await resolve_persona_request(request, user, manager=None)

    assert request.enabled_skills == ["custom"]
    assert request.persona_snapshot is None
    assert request.persona_system_prompt is None


@pytest.mark.asyncio
async def test_resolve_persona_request_overwrites_client_persona_fields_from_preset() -> None:
    snapshot = PersonaPresetSnapshot(
        preset_id="preset-1",
        name="Planner",
        system_prompt="Plan first.",
        skill_names=["planning"],
        missing_skill_names=["missing"],
        version=2,
    )

    class _FakeManager:
        async def use_preset(self, preset_id: str, *, user_id: str, is_admin: bool):
            assert preset_id == "preset-1"
            assert user_id == "user-1"
            assert is_admin is True
            return snapshot

    request = AgentRequest(
        message="hello",
        persona_preset_id="preset-1",
        enabled_skills=["custom"],
        persona_snapshot=PersonaPresetSnapshot(
            preset_id="evil",
            name="Evil",
            system_prompt="inject me",
            skill_names=["evil"],
            missing_skill_names=[],
            version=9,
        ),
        persona_system_prompt="inject me",
    )
    user = TokenPayload(
        sub="user-1",
        username="tester",
        permissions=["chat:write", "persona_preset:admin"],
    )

    await resolve_persona_request(request, user, manager=_FakeManager())

    assert request.persona_snapshot == snapshot
    assert request.persona_system_prompt == "Plan first."
    assert request.enabled_skills == ["planning"]


def test_persona_prompt_section_is_deterministic() -> None:
    assert build_persona_prompt_section("Plan first.") == "## Persona Preset\n\nPlan first."
    assert build_persona_prompt_section("  \n") == ""


def test_search_context_filters_skills_and_files_by_whitelist() -> None:
    context = SearchAgentContext(enabled_skills=["keep"])
    context.skills = [
        {"name": "keep", "enabled": True},
        {"name": "drop", "enabled": True},
    ]
    context.skill_files = {
        "/keep/SKILL.md": object(),
        "/drop/SKILL.md": object(),
        "/drop/notes.md": object(),
    }

    context.apply_skill_filters()

    assert context.skills == [{"name": "keep", "enabled": True}]
    assert list(context.skill_files) == ["/keep/SKILL.md"]
