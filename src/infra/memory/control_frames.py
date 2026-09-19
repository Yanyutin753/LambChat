"""Shared sanitization contract for model/runtime control frames."""

from __future__ import annotations

import re

CONTROL_FRAME_NAMES: tuple[str, ...] = (
    "memory_context",
    "memory_index",
    "memory_index_context",
    "turn_context",
    "session_todo_context",
    "active_goal_context",
    "active_goal",
    "required_skills",
    "code_interpreter_routing",
    "env_var_keys_context",
    "sandbox_workspace_context",
)

_FRAME_ALTERNATION = "|".join(re.escape(name) for name in CONTROL_FRAME_NAMES)

# Tags are stripped from individual untrusted fields and queries.
CONTROL_FRAME_TAG_RE = re.compile(
    rf"</?(?:{_FRAME_ALTERNATION})(?:\s[^>]*)?\s*/?>",
    re.IGNORECASE,
)

# Complete injected blocks are removed before durable memory extraction or
# when rebuilding a generated tool description.  The captured tag name keeps
# opening/closing pairs matched even when a provider changes the casing.
CONTROL_FRAME_BLOCK_RE = re.compile(
    rf"\s*<({_FRAME_ALTERNATION})(?:\s[^>]*)?>.*?</\1>\s*",
    re.DOTALL | re.IGNORECASE,
)


def escape_control_frame_tags(value: object) -> str:
    """Escape user-authored control-frame tags without altering other text.

    Model-facing user content can contain literal markup that happens to use
    an internal frame name. Escaping only those tags keeps the visible text
    recognizable while preventing it from being mistaken for trusted runtime
    context or stripped by durable-memory extraction.
    """

    text = str(value or "")
    return CONTROL_FRAME_TAG_RE.sub(lambda match: f"&lt;{match.group(0)[1:-1]}&gt;", text)
