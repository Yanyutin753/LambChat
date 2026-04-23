from src.agents.core.subagent_prompts import SUBAGENT_PROMPT, SUBAGENT_TASK_GUIDE


def test_subagent_prompt_requires_structured_handoff_notes() -> None:
    required_sections = [
        "## Handoff Notes",
        "Goal:",
        "What I checked:",
        "Key findings:",
        "Files / tools touched:",
        "Decisions or assumptions:",
        "Risks / blockers:",
        "Suggested next step:",
        "Memory-worthy notes:",
    ]

    for section in required_sections:
        assert section in SUBAGENT_PROMPT


def test_main_agent_guide_requires_synthesizing_subagent_results() -> None:
    required_guidance = [
        "synthesize",
        "deduplicate",
        "conflict",
        "handoff notes",
    ]

    guide = SUBAGENT_TASK_GUIDE.lower()
    for phrase in required_guidance:
        assert phrase in guide
