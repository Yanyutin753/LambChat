"""Compact shared prompts for main agents and subagents."""

from src.agents.core.prompt_policy import (
    ARTIFACT_POLICY,
    HANDOFF_POLICY,
    PROGRESS_POLICY,
    SAFETY_POLICY,
    SUBAGENT_DISPATCH_POLICY,
    WORKFLOW_POLICY,
    WORKSPACE_POLICY,
)
from src.kernel.config.base import settings

FILE_WORKSPACE_GUIDE = WORKSPACE_POLICY
FILE_REVEAL_GUIDE = ARTIFACT_POLICY
SAFETY_AND_VERIFICATION_GUIDE = SAFETY_POLICY
TOOL_PROGRESS_GUIDE = PROGRESS_POLICY
TODO_LIST_GUIDE = PROGRESS_POLICY
WORKFLOW_SECTION = WORKFLOW_POLICY
SUBAGENT_TASK_GUIDE = SUBAGENT_DISPATCH_POLICY

MAIN_AGENT_PROMPT_SECTIONS: tuple[str, ...] = (
    WORKFLOW_POLICY,
    SUBAGENT_DISPATCH_POLICY,
)

# 前端 i18n 支持的界面语言 → 提示词用语名（zh 为简体）
RESPONSE_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "zh": "Simplified Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "ru": "Russian",
}


def build_response_language_section(language: str | None) -> str:
    """把用户界面 locale 固定为模型回复语言。

    只在能识别界面语言时注入；识别不了返回空串（不改变模型跟随用户
    消息语言的默认行为）。按 OpenAI 提示词指南显式给出例外条件而非
    一刀切规则。实测（GLM-5.3）中文消息的先验会压过宽松的例外措辞
    （"unless the user asks"会被解读成"用户用中文提问=要求中文"），
    因此必须显式声明界面语言优先于消息/引用内容语言。
    """
    language_name = RESPONSE_LANGUAGE_NAMES.get((language or "").strip().lower())
    if not language_name:
        return ""
    return (
        "### Response Language\n"
        "- Always respond in "
        f"{language_name} regardless of the language of the user's message "
        "or any quoted content.\n"
        "- Switch to another language only when the user explicitly requests it.\n"
        "- Keep code, commands, error messages, file paths, and technical "
        "identifiers unchanged."
    )


AUTO_MODE_PROMPT_SECTION = """### Auto Mode
Work autonomously with reasonable assumptions; `ask_human` is unavailable. Preserve safety boundaries, and report decisions and verification."""


def get_memory_guide() -> str:
    from src.kernel.config import settings

    if getattr(settings, "ENABLE_MEMORY_VFS", False):
        from src.infra.memory.client.types import NATIVE_MEMORY_GUIDE_VFS

        return NATIVE_MEMORY_GUIDE_VFS
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
