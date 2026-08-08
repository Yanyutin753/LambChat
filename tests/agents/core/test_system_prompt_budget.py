from src.agents.core.persona import build_persona_prompt_section
from src.agents.core.prompt_policy import (
    SANDBOX_RUNTIME_POLICY,
    SANDBOX_STORAGE_POLICY,
    SUBAGENT_DISPATCH_POLICY,
    WORKFLOW_POLICY,
)
from src.agents.core.todo_middleware import create_todo_middleware
from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE
from src.infra.skill.loader import format_skills_prompt
from src.infra.tool.deferred_manager import DEFERRED_TOOL_SEARCH_GUIDE
from src.infra.tool.sandbox_mcp_prompt import _format_tools_list_sections


def test_owned_prompt_blocks_save_twenty_percent_of_full_baseline() -> None:
    skills = [
        {"name": "agentic", "description": "Conversational agent workflows."},
        {"name": "ant", "description": "Enterprise interface design."},
        {"name": "publisher", "description": "Publish social content."},
    ]
    sandbox_sections, total = _format_tools_list_sections(
        {
            "servers": [
                {
                    "name": "demo",
                    "status": "ok",
                    "tools": [{"name": "run", "description": "Run demo"}],
                }
            ]
        }
    )
    assert total == 1

    blocks = (
        SANDBOX_STORAGE_POLICY,
        SANDBOX_RUNTIME_POLICY.format(work_dir="/home/user/sessions/example"),
        WORKFLOW_POLICY,
        SUBAGENT_DISPATCH_POLICY,
        build_persona_prompt_section(None),
        format_skills_prompt(skills),
        NATIVE_MEMORY_GUIDE,
        DEFERRED_TOOL_SEARCH_GUIDE,
        sandbox_sections[0],
        create_todo_middleware().system_prompt,
    )

    # Pre-change owned sample: 8,274. Required saving: 2,232 characters.
    assert sum(len(block) for block in blocks) <= 6_042
