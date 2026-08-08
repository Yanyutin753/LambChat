"""Compact shared prompts for main agents and subagents."""

from src.agents.core.prompt_policy import (
    ARTIFACT_POLICY,
    HANDOFF_POLICY,
    PROGRESS_POLICY,
    SAFETY_POLICY,
    SUBAGENT_DISPATCH_POLICY,
    TOOL_DISCOVERY_POLICY,
    WORKFLOW_POLICY,
    WORKSPACE_POLICY,
)
from src.kernel.config.base import settings

FILE_WORKSPACE_GUIDE = WORKSPACE_POLICY
FILE_REVEAL_GUIDE = ARTIFACT_POLICY
SAFETY_AND_VERIFICATION_GUIDE = SAFETY_POLICY
TOOL_DISCOVERY_GUIDE = TOOL_DISCOVERY_POLICY
TOOL_PROGRESS_GUIDE = PROGRESS_POLICY
TODO_LIST_GUIDE = PROGRESS_POLICY
WORKFLOW_SECTION = WORKFLOW_POLICY
SUBAGENT_TASK_GUIDE = SUBAGENT_DISPATCH_POLICY

MAIN_AGENT_PROMPT_SECTIONS: tuple[str, ...] = (
    WORKFLOW_POLICY,
    SUBAGENT_DISPATCH_POLICY,
)

AUTO_MODE_PROMPT_SECTION = """### Auto Mode
Work autonomously with reasonable assumptions; `ask_human` is unavailable. Preserve safety boundaries, and report decisions and verification."""


def get_memory_guide() -> str:
    from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE

    return NATIVE_MEMORY_GUIDE


_SUBAGENT_BASE = """You are a subagent completing a scoped objective. Stay within scope, prefer evidence, name uncertainty, verify checkable claims, and hand results to the main agent rather than promising the user a final outcome."""

DEFAULT_SUBAGENT_PROMPT = "\n\n".join((_SUBAGENT_BASE, WORKFLOW_POLICY, HANDOFF_POLICY))
DETAILED_SUBAGENT_PROMPT = "\n\n".join(
    (
        _SUBAGENT_BASE,
        "Your activity is recorded. Investigate thoroughly enough for a reliable handoff.",
        WORKFLOW_POLICY,
        HANDOFF_POLICY,
    )
)
SUBAGENT_PROMPT = DETAILED_SUBAGENT_PROMPT


def build_subagent_system_prompt(base_prompt: str, *sections: str | None) -> str:
    parts = [base_prompt.strip()]
    parts.extend(section.strip() for section in sections if section and section.strip())
    return "\n\n".join(parts)


SPECIALIZED_SUBAGENT_NAMES: tuple[str, ...] = (
    "codebase-investigator",
    "implementation-worker",
    "verification-runner",
    "researcher",
)

SPECIALIZED_SUBAGENT_DESCRIPTIONS: dict[str, str] = {
    "codebase-investigator": "Inspect relevant files, call paths, patterns, risks, and tests without editing.",
    "implementation-worker": "Make a small scoped change from a clear work order and verify it.",
    "verification-runner": "Run focused checks, diagnose failures, and do not change production files.",
    "researcher": "Research current external facts from primary sources with date/version caveats.",
}

CODEBASE_INVESTIGATOR_PROMPT = build_subagent_system_prompt(
    DETAILED_SUBAGENT_PROMPT,
    "## Codebase Investigator\nDo not edit. Report relevant files, current behavior, patterns, risks, and investigation gaps.",
)
IMPLEMENTATION_WORKER_PROMPT = build_subagent_system_prompt(
    DETAILED_SUBAGENT_PROMPT,
    "## Implementation Worker\nMake only the scoped change. Preserve architecture and report files changed, verification, and risks.",
)
VERIFICATION_RUNNER_PROMPT = build_subagent_system_prompt(
    DETAILED_SUBAGENT_PROMPT,
    "## Verification Runner\nDo not change production files. Report commands, pass/fail status, failure analysis, blockers, and next diagnostic.",
)
RESEARCH_SUBAGENT_PROMPT = build_subagent_system_prompt(
    DETAILED_SUBAGENT_PROMPT,
    "## Researcher\nUse primary sources where possible. Report source-backed findings, date/version caveats, confidence, and implications.",
)


def build_role_subagent_section(
    role_name: str,
    role_system_prompt: str,
    team_name: str | None = None,
    team_instructions: str | None = None,
    role_instructions: str | None = None,
    task_objective: str | None = None,
) -> str:
    parts = [
        "## Persona",
        f"You are a subagent in the role of **{role_name}**.",
        role_system_prompt,
    ]
    if team_name:
        parts.append(f"### Team: {team_name}")
    if team_instructions:
        parts.append(f"### Team Instructions\n{team_instructions}")
    if role_instructions:
        parts.append(f"### Role Instructions\n{role_instructions}")
    if task_objective:
        parts.append(f"### Task Objective\n{task_objective}")
    return "\n\n".join(parts)


def build_role_subagent_prompt(
    role_name: str,
    role_system_prompt: str,
    team_name: str | None = None,
    team_instructions: str | None = None,
    role_instructions: str | None = None,
    task_objective: str | None = None,
) -> str:
    return build_subagent_system_prompt(
        SUBAGENT_PROMPT,
        build_role_subagent_section(
            role_name,
            role_system_prompt,
            team_name,
            team_instructions,
            role_instructions,
            task_objective,
        ),
    )


if settings.ENABLE_SCHEDULED_TASK:
    MAIN_AGENT_PROMPT_SECTIONS += (
        "Scheduled reminders/reports are supported through `scheduled_task_create` when requested.",
    )
