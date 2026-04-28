from src.infra.assistant.prompt import build_assistant_prompt_sections


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
