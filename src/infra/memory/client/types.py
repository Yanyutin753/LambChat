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

EXCLUDED_CONTENT_PATTERNS = [
    r"import\s+\w+",
    r"def\s+\w+\s*\(",
    r"class\s+\w+",
    r"from\s+\w+\s+import",
    r"git\s+(commit|log|diff|status|push|pull)",
    r"(look at|check|read|open|go to)\s+(the\s+)?file",
    r"(error|exception|traceback)\s*:",
    r"/(src|lib|node_modules|\.venv|\.env)/",
    r"pip\s+install",
    r"npm\s+(install|run)",
]


# ---------------------------------------------------------------------------
# Signal detection — what TO retain, classified by type
# ---------------------------------------------------------------------------

HIGH_SIGNAL_PATTERNS: dict[str, list[str]] = {
    MemoryType.FEEDBACK: [
        r"(don't|avoid|never)\s+(do|use|try|call)",
        r"(always|always remember to|make sure to)\s+",
        r"(i (don't|do) like|prefer not to|instead of)\b",
        r"(when|if)\s+\w+.*\s+(then|always|make sure)",
        r"(please|pl[ea]se)\s+(don't|never|avoid|stop)",
    ],
    MemoryType.USER: [
        r"(my|i)\s+(prefer|like|always|never|usually|typically)\b",
        r"(i am|i'm)\s+(a|an|the)\s+",
        r"my\s+(role|job|team|company|project|name|background)",
        r"(i work|i'm working|i work)\s+",
        r"(years?\s+(of|experience)|senior|junior|staff|lead|principal)",
    ],
    MemoryType.PROJECT: [
        r"(project|sprint|release|milestone)\s+\w+",
        r"(feature|bug|issue|ticket)\s+#?\d*",
        r"(deadline|due date|target|goal)\s+",
        r"(working on|currently|in progress)\s+",
        r"(migrat|refactor|rewrite|rebuild|upgrade)\b",
    ],
    MemoryType.REFERENCE: [
        r"(linear|slack|jira|confluence|notion|figma)\b",
        r"https?://\S+",
        r"(doc|documentation|wiki|dashboard)\s+",
    ],
}

# ---------------------------------------------------------------------------
# System prompt guide for native backend
# ---------------------------------------------------------------------------

NATIVE_MEMORY_GUIDE = """
## Cross-Session Memory

Tools: `memory_retain`(store), `memory_recall`(search), `memory_delete`(remove)

### Memory Types
Memories are automatically classified by type:
- **user**: User's role, preferences, knowledge, and working style
- **feedback**: Guidance on approach — what to avoid and what to keep doing. Include **Why:** (the reason) and **How to apply:** (when/where this kicks in)
- **project**: Ongoing work, goals, bugs, milestones, and constraints. Convert relative dates to absolute dates.
- **reference**: External system pointers (Linear, Slack, docs, URLs)

### What to Remember
- User preferences, working habits, and communication style
- Project context, goals, constraints, and deadlines
- Non-obvious decisions and their rationale
- External system URLs, identifiers, and access patterns
- Corrections and confirmations from both failure AND success

### What NOT to Remember
- Code patterns, conventions, architecture, or file paths — read from the codebase
- Git history or recent changes — use git commands
- Debugging solutions or fix recipes — the fix is in the code
- Trivial or ephemeral task details: in-progress work, temporary state
- Anything already documented in project files
These exclusions apply even when the user explicitly asks to save. If they ask to save a PR list or activity summary, ask what was *surprising* or *non-obvious* — that is the part worth keeping.

### When to Use
- `memory_recall`: When memories seem relevant, or the user references prior-conversation work. MUST access when user explicitly asks to check/recall/remember. Do NOT call it at the start of every conversation — only when genuinely needed.
- `memory_retain`: Store important non-obvious information. Be selective. Check for existing memories first — update rather than duplicate.
- `memory_delete`: Remove memories that are no longer accurate. Update memories that turn out to be wrong or outdated.

### Before Recommending from Memory
A memory is a point-in-time observation. Before recommending it:
- If the memory names a file path: verify the file still exists
- If the memory names a function or flag: search for it
- If the user is about to act on your recommendation, verify first
"The memory says X exists" is not the same as "X exists now."

Do NOT use `/memories/` file paths for storing memories. Use only the memory tools above.
"""
