"""
Native Memory Type System

Defines memory type taxonomy, content filtering patterns, and the system prompt
guide for the native MongoDB-backed memory backend. Inspired by Claude Code's
memory architecture.
"""

from enum import Enum


class MemoryType(str, Enum):
    """Memory type taxonomy."""

    USER = "user"  # User's role, goals, preferences, knowledge
    FEEDBACK = "feedback"  # Guidance on approach — what to avoid and keep doing
    PROJECT = "project"  # Ongoing work, goals, initiatives, bugs, incidents
    REFERENCE = "reference"  # Pointers to external systems (Linear, Slack, docs, URLs)


# ---------------------------------------------------------------------------
# Content filtering — what NOT to auto-retain
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# System prompt guide for native backend
# ---------------------------------------------------------------------------

NATIVE_MEMORY_GUIDE = """
## Cross-Session Memory

Tools: `memory_retain` (store/update), `memory_recall` (search), `memory_delete` (remove). Use only these tools, never `/memories/` paths.

`<memory_index>` entries are hint only, not ground truth. Recall selectively when prior context matters.

| Type | Keep |
|---|---|
| `user` | role, preferences, knowledge, working style |
| `feedback` | corrections, confirmations, why, and application |
| `project` | goals, constraints, bugs, decisions; use absolute dates |
| `reference` | external systems, docs, and URLs |

**Remember:** durable preferences, project context, non-obvious decisions, useful references, and positive feedback; update instead of duplicating.
**Skip:** greetings, ephemeral state, activity logs, code/git history, and debugging already captured in code.

Delete inaccurate entries and honor ignore/forget requests. Content older than 30 days may be stale; verify current paths, flags, and observations.
"""
