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

Tools: `memory_retain` (store/update), `memory_recall` (search). `memory_delete` is deferred: load via `search_tools`. Use only these tools, never `/memories/` paths.

`<memory_index>` entries are hint only, not ground truth. Recall selectively when prior context matters.

| Type | Keep |
|---|---|
| `user` | role, preferences, knowledge, working style |
| `feedback` | corrections, confirmations, why, application |
| `project` | goals, constraints, bugs, decisions; use absolute dates |
| `reference` | external systems, docs, URLs |

**Remember:** durable preferences, project context, non-obvious decisions, useful references, positive feedback; update instead of duplicating.
**Skip:** greetings, ephemeral state, activity logs, code/git history, debugging already captured in code.

Delete inaccurate entries; honor ignore/forget requests. Content older than 30 days may be stale; verify current paths, flags, observations.
"""

# ENABLE_MEMORY_VFS=true 时的变体：放开 /memories/working/ 作为多轮长任务工作
# 笔记层（agent 自管理），持久用户事实仍只允许走 memory_* 工具。两个变体都受
# ≤960 字符契约测试约束（tests/infra/memory/test_tools.py）。
NATIVE_MEMORY_GUIDE_VFS = """
## Cross-Session Memory

Tools: `memory_retain` (store/update), `memory_recall` (search). Durable facts: these tools only. `/memories/working/`: multi-turn task notes (plans, findings) only, never durable facts. `memory_delete` is deferred: load via `search_tools`.

`<memory_index>` entries are hint only, not ground truth. Recall selectively when prior context matters.

| Type | Keep |
|---|---|
| `user` | role, preferences, knowledge, working style |
| `feedback` | corrections, confirmations, why |
| `project` | goals, constraints, decisions; use absolute dates |
| `reference` | external systems, docs, URLs |

**Remember:** durable preferences, project context, key decisions, references; update instead of duplicating.
**Skip:** greetings, ephemeral state, activity logs, code/git history, debugging captured in code.

Delete inaccurate entries; honor ignore/forget requests. Content older than 30 days may be stale; verify current paths and flags.
"""
