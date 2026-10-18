import pytest

from src.agents.core.subagent_prompts import (
    DEFAULT_SUBAGENT_PROMPT,
    IMPLEMENTATION_WORKER_PROMPT,
    MAIN_AGENT_PROMPT_SECTIONS,
)


@pytest.mark.parametrize(
    "prompt",
    [
        "\n\n".join(MAIN_AGENT_PROMPT_SECTIONS),
        DEFAULT_SUBAGENT_PROMPT,
        IMPLEMENTATION_WORKER_PROMPT,
    ],
)
def test_tool_work_reaches_execution_before_drafting_the_entire_implementation(prompt):
    assert "next concrete tool action" in prompt
    assert "do not draft the entire implementation in private reasoning" in prompt
    assert prompt.count("next concrete tool action") == 1
