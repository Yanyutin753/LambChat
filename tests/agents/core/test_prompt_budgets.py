from __future__ import annotations

import pytest

from src.agents.core.subagent_prompts import (
    MAIN_AGENT_PROMPT_SECTIONS,
    SUBAGENT_PROMPT,
    WORKFLOW_SECTION,
)
from src.agents.search_agent.prompt import SANDBOX_SYSTEM_PROMPT
from src.infra.skill.loader import build_skills_prompt


def test_static_prompt_budgets() -> None:
    main_sandbox_static_prompt = "\n\n".join((SANDBOX_SYSTEM_PROMPT, *MAIN_AGENT_PROMPT_SECTIONS))

    assert len(main_sandbox_static_prompt) <= 6000
    assert len(WORKFLOW_SECTION) <= 3800
    assert len(SUBAGENT_PROMPT) <= 4800


@pytest.mark.asyncio
async def test_large_skill_inventory_budget() -> None:
    skills = [
        {"name": f"skill-{index:02d}", "description": "Verbose description " * 20}
        for index in range(25)
    ]

    assert len(await build_skills_prompt(skills)) <= 1200
