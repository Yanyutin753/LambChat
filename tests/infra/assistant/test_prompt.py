from src.infra.assistant.prompt import (
    build_assistant_prompt_sections,
    build_runtime_assistant_prompt_summary,
    build_system_prompt_with_assistant,
    resolve_runtime_assistant_prompt,
)


def test_build_assistant_prompt_sections_puts_assistant_before_skills_and_memory() -> None:
    sections = build_assistant_prompt_sections(
        assistant_prompt="assistant block",
        skills_prompt="skills block",
        memory_guide="memory block",
    )

    assert sections == ("assistant block", "skills block", "memory block")


def test_build_assistant_prompt_sections_skips_empty_values() -> None:
    sections = build_assistant_prompt_sections(
        assistant_prompt="",
        skills_prompt="skills block",
        memory_guide="",
    )

    assert sections == ("skills block",)


def test_resolve_runtime_assistant_prompt_prefers_explicit_value() -> None:
    prompt = resolve_runtime_assistant_prompt(
        assistant_prompt="explicit assistant prompt",
        agent_options={"_assistant_prompt": "hidden prompt"},
    )

    assert prompt == "explicit assistant prompt"


def test_resolve_runtime_assistant_prompt_falls_back_to_agent_options_snapshot() -> None:
    prompt = resolve_runtime_assistant_prompt(
        assistant_prompt="",
        agent_options={"_assistant_prompt": "snapshot prompt"},
    )

    assert prompt == "snapshot prompt"


def test_resolve_runtime_assistant_prompt_ignores_non_string_values() -> None:
    prompt = resolve_runtime_assistant_prompt(
        assistant_prompt="",
        agent_options={"_assistant_prompt": 123},
    )

    assert prompt == ""


def test_build_system_prompt_with_assistant_appends_assistant_block() -> None:
    prompt = build_system_prompt_with_assistant(
        base_system_prompt="base system prompt",
        assistant_prompt="assistant preset",
    )

    assert prompt == "base system prompt\n\nassistant preset"


def test_build_system_prompt_with_assistant_skips_empty_assistant_prompt() -> None:
    prompt = build_system_prompt_with_assistant(
        base_system_prompt="base system prompt",
        assistant_prompt="",
    )

    assert prompt == "base system prompt"


def test_build_runtime_assistant_prompt_summary_reports_active_snapshot() -> None:
    summary = build_runtime_assistant_prompt_summary(
        assistant_name="Planner",
        assistant_prompt="You are a planner.",
        source="session_snapshot",
    )

    assert summary == "assistant=Planner source=session_snapshot prompt_chars=18"


def test_build_runtime_assistant_prompt_summary_reports_empty_state() -> None:
    summary = build_runtime_assistant_prompt_summary(
        assistant_name="",
        assistant_prompt="",
        source="none",
    )

    assert summary == "assistant=none source=none prompt_chars=0"
