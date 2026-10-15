"""Supported agents and shared prompt regressions."""


def test_registered_agent_catalog():
    from src.agents import discover_agents
    from src.agents.core.base import list_registered_agents

    discover_agents()
    assert set(list_registered_agents()) == {"search", "quick", "team"}


def test_subagent_prompt_unchanged():
    from src.agents.core.subagent_prompts import DEFAULT_SUBAGENT_PROMPT, SUBAGENT_PROMPT

    assert "Handoff Notes" in SUBAGENT_PROMPT
    assert "Handoff Notes" in DEFAULT_SUBAGENT_PROMPT


def test_main_agent_prompt_sections_unchanged():
    from src.agents.core.subagent_prompts import MAIN_AGENT_PROMPT_SECTIONS

    assert any("task" in str(s).lower() for s in MAIN_AGENT_PROMPT_SECTIONS)
    assert "Handoff Notes" not in str(MAIN_AGENT_PROMPT_SECTIONS)


def test_shared_agent_prompts_include_privacy_output_policy():
    from src.agents.core.subagent_prompts import MAIN_AGENT_PROMPT_SECTIONS, SUBAGENT_PROMPT

    combined_prompt = "\n".join((*MAIN_AGENT_PROMPT_SECTIONS, SUBAGENT_PROMPT))

    assert "Privacy-Safe Output" in combined_prompt
    assert "Do not repeat sensitive personal data" in combined_prompt
    assert "access tokens" in combined_prompt


def test_build_role_subagent_prompt_exists():
    from src.agents.core.subagent_prompts import build_role_subagent_prompt

    prompt = build_role_subagent_prompt(
        role_name="Test",
        role_system_prompt="You test things.",
    )
    assert "Test" in prompt
    assert "Handoff Notes" in prompt
