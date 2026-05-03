from __future__ import annotations

from src.agents.core.persona import build_persona_prompt_section
from src.agents.search_agent.context import SearchAgentContext
from src.api.routes.chat import build_conversation_config
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.persona_preset import PersonaPresetSnapshot


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
