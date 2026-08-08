"""Persona prompt helpers.

角色身份通过 middleware 注入，与基础提示词解耦。
通过 register_harness_profile 移除 BASE_AGENT_PROMPT 中的身份声明，
让 persona 系统完全控制角色身份，不再冲突。

最终 system message 结构：
  [Block 0] SANDBOX/DEFAULT/FAST_SYSTEM_PROMPT + BEHAVIOR_GUIDE      ← 全局稳定
  [Block 1-3] deepagents 内部 (write_todos, conventions, task)        ← 全局稳定
  [Block 4]   ## Persona (角色 + 行为合并)                             ← 同 persona 缓存命中
  [Block 5]   Skills                                                  ← 同 session 缓存命中
  [Block 6]   Memory guide                                            ← 同用户缓存命中
  [Block 7+]  Memory index / Tool search                              ← 每 turn 变化
"""

import importlib
from typing import Any

from src.kernel.config.base import settings

_deepagents: Any = None
try:
    _deepagents = importlib.import_module("deepagents")
except ImportError:  # pragma: no cover - compatibility with older deepagents builds
    pass

_HarnessProfile = getattr(_deepagents, "HarnessProfile", None) if _deepagents is not None else None
_register_harness_profile = (
    getattr(_deepagents, "register_harness_profile", None) if _deepagents is not None else None
)


DEFAULT_ROLE = "You are an intelligent assistant with tools and skills."

_PERSONA_HEADING = "## Persona"


# ---------------------------------------------------------------------------
# Strip the identity line from BASE_AGENT_PROMPT so persona has full control.
#
# Original first line: "You are a deep agent, an AI assistant that helps
# users accomplish tasks using tools. You respond with text and tool calls.
# The user can see your responses and tool outputs in real time."
#
# We keep everything else (Core Behavior, Professional Objectivity, Doing
# Tasks, etc.) because those are valuable behavioral guardrails that don't
# conflict with persona roles.
#
# Runtime provider keys come from the concrete LangChain model classes rather
# than LambChat's configured provider slugs. These three keys cover every
# model class constructed by LLMClient.
# ---------------------------------------------------------------------------
_HARNESS_PROFILE_PROVIDERS = ("anthropic", "openai", "google_genai")


def _build_behavior_guide() -> str:
    """Build response-style and persistence guidance without workflow duplication."""
    scheduled_task_section = ""
    if settings.ENABLE_SCHEDULED_TASK:
        scheduled_task_section = (
            " Use `scheduled_task_create` for requested reminders, notifications, or reports."
        )

    return f"""You have tools and may respond with text or tool calls.{scheduled_task_section}

## Response Style
- Be concise, direct, and objective; omit ceremonial preambles and unsupported praise.
- Match the user's expertise and requested detail. Explain an approach first only when asked.
- Correct mistakes respectfully and distinguish evidence from assumptions.

## Task Persistence
Read enough context to understand existing patterns, act, and keep working until done or genuinely blocked. When a failure repeats, diagnose the cause instead of retrying unchanged. Report a blocker plainly."""


_BEHAVIOR_GUIDE = _build_behavior_guide()

if _HarnessProfile is not None and _register_harness_profile is not None:
    # Register on import — this is idempotent (additive merge).
    _profile = _HarnessProfile(base_system_prompt=_BEHAVIOR_GUIDE)
    for _provider in _HARNESS_PROFILE_PROVIDERS:
        _register_harness_profile(_provider, _profile)


def split_persona_prompt(system_prompt: str) -> tuple[str, str]:
    """Split a persona system_prompt into role identity and behavior body.

    The first paragraph (before the first blank line) is the *role identity*.
    Everything after the first blank line is *behavior instructions*.

    Returns (role, behavior).  Either may be empty.
    """
    text = system_prompt.strip()
    if not text:
        return "", ""

    parts = text.split("\n\n", 1)
    role = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""
    return role, body


def build_persona_prompt_sections(system_prompt: str | None) -> list[str]:
    """Build persona sections as content blocks for injection.

    Role and behavior are merged into a **single block** for stronger signal.
    Splitting into two blocks dilutes the persona identity — the model may
    latch onto the default role before reaching a separate behavior block.

    Always returns exactly one block (with default role when no persona).
    """
    role, body = split_persona_prompt(system_prompt or "")
    effective_role = role if role else DEFAULT_ROLE

    if body:
        return [f"{_PERSONA_HEADING}\n\n{effective_role}\n\n{body}"]
    return [f"{_PERSONA_HEADING}\n\n{effective_role}"]


def build_persona_prompt_section(system_prompt: str | None) -> str:
    """Legacy single-section builder. Prefer ``build_persona_prompt_sections``."""
    return build_persona_prompt_sections(system_prompt)[0]
