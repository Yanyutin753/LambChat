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
    # Chinese assistant self-talk / internal monologue
    r"^(让我|我来|我来帮|让我来|让我检查|让我看看|让我搜|搜索一下|查找一下|我来分析|我来搜索)",
    r"^(正在搜索|正在查找|正在检查|正在分析|正在读取|正在执行)",
    # Chinese greetings / farewells
    r"^(你好|您好|嗨|早上好|下午好|晚上好|再见|拜拜|谢谢)",
]


# ---------------------------------------------------------------------------
# Signal detection — what TO retain, classified by type
# ---------------------------------------------------------------------------

HIGH_SIGNAL_PATTERNS: dict[str, list[str]] = {
    MemoryType.FEEDBACK: [
        # Negative: corrections, rejections
        r"(don't|avoid|never)\s+(do|use|try|call)",
        r"(always|always remember to|make sure to)\s+",
        r"(i (don't|do) like|prefer not to|instead of)\b",
        r"(when|if)\s+\w+.*\s+(then|always|make sure)",
        r"(please|pl[ea]se)\s+(don't|never|avoid|stop)",
        # Positive: confirmations — quieter but equally important
        r"(yes\s+exactly|exactly|perfect|right\s+call|good\s+approach|that'?s?\s+right)",
        r"(keep\s+doing|keep\s+it|this\s+is\s+(the\s+)?right|go\s+with\s+this)",
        r"(worked\s+well|worked\s+great|looks\s+good|that'?s?\s+(the\s+)?way)",
        r"(noted|got\s+it|understood|i\s+see|makes\s+sense)\s+[,.!]",
        # Chinese negative feedback
        r"(不要|别|避免|千万不).*(做|用|试|写|改)",
        r"(总是要|一定要|务必|每次都要)",
        r"(我不喜欢|更喜欢|不如|不如用)",
        # Chinese positive feedback
        r"(对[，,]就是这样|完全正确|很好|继续保持|没问题|就这样)",
        r"(做得好|这正是我想要|没错|对的|可以|行)",
        r"(理解了|明白了|有道理|说得对)",
    ],
    MemoryType.USER: [
        r"(my|i)\s+(prefer|like|always|never|usually|typically)\b",
        r"(i am|i'm)\s+(a|an|the)\s+",
        r"my\s+(role|job|team|company|project|name|background)",
        r"(i work|i'm working|i work)\s+",
        r"(years?\s+(of|experience)|senior|junior|staff|lead|principal)",
        # Chinese user identity/preferences
        r"(我是|我叫).*(工程师|开发|设计师|产品|经理|架构师|程序员)",
        r"我的(角色|工作|团队|公司|项目|名字|背景)",
        r"(我用|我喜欢|我习惯|偏好).*(框架|工具|语言|编辑器|技术)",
        r"(年经验|工作经验|从业|开发经验)",
    ],
    MemoryType.PROJECT: [
        r"(project|sprint|release|milestone)\s+\w+",
        r"(feature|bug|issue|ticket)\s+#?\d*",
        r"(deadline|due date|target|goal)\s+",
        r"(working on|currently|in progress)\s+",
        r"(migrat|refactor|rewrite|rebuild|upgrade)\b",
        # Chinese project context
        r"(项目|版本|迭代|里程碑|功能|需求|缺陷|工单)",
        r"(截止日期|目标|交付|上线|发布)",
        r"(正在做|进行中|开发中|重构|迁移|升级|测试中)",
    ],
    MemoryType.REFERENCE: [
        r"(linear|slack|jira|confluence|notion|figma)\b",
        r"https?://\S+",
        r"(doc|documentation|wiki|dashboard)\s+",
        # Chinese references
        r"(文档地址|系统地址|链接|接口|端点)",
        r"(监控|看板|面板|仪表盘)",
    ],
}

# ---------------------------------------------------------------------------
# System prompt guide for native backend
# ---------------------------------------------------------------------------

NATIVE_MEMORY_GUIDE = """
## Cross-Session Memory

Tools: `memory_retain`(store), `memory_recall`(search), `memory_delete`(remove), `memory_consolidate`(cleanup)

### Memory Index
The system prompt contains a `<memory_index>` showing your stored memories as:
`- title (short_id, age)`
Each line is only a hint, not the full memory.
The label is a compact index title, and the short id is only for disambiguation.
Do not treat the index itself as ground truth.
If an item seems relevant, use `memory_recall` with the title or topic to fetch the full memory.
Do not mention unrelated index items just because they are present.

### Memory Types
Memories are automatically classified by type:
- **user**: User's role, preferences, knowledge, and working style
- **feedback**: Guidance on approach — what to avoid AND what to keep doing. Record from failure AND success: if you only save corrections, you'll drift away from approaches the user has validated and grow overly cautious. Confirmations are quieter — watch for "yes exactly", "perfect", "keep doing that", "right call". Include **Why:** (the reason) and **How to apply:** (when/where this kicks in)
- **project**: Ongoing work, goals, bugs, milestones, and constraints. Convert relative dates to absolute dates ("yesterday" → "2026-04-01").
- **reference**: External system pointers (Linear, Slack, docs, URLs)

### What to Remember
- User preferences, working habits, and communication style
- Project context, goals, constraints, and deadlines
- Non-obvious decisions and their rationale
- External system URLs, identifiers, and access patterns
- Both corrections AND positive confirmations (e.g. "yes exactly, that's the right approach")

### What NOT to Remember
- Code patterns, conventions, architecture, or file paths — read from the codebase
- Git history or recent changes — use git commands
- Debugging solutions or fix recipes — the fix is in the code
- Trivial or ephemeral task details: in-progress work, temporary state
- Anything already documented in project files
- Activity logs, PR lists, or summary recaps — even when the user asks to save these, ask what was *surprising* or *non-obvious*
These exclusions apply **even when the user explicitly asks to save**. Extract the non-obvious kernel, not the full content.

### When to Use
- `memory_recall`: When a memory's title seems relevant, or the user references prior-conversation work. MUST access when user explicitly asks to check/recall/remember. Do NOT call it at the start of every conversation — only when genuinely needed.
- `memory_retain`: Store important non-obvious information. Be selective. Prefer explicit contexts such as `user_identity`, `project_constraint`, `project_status`, `feedback_rule`, or `reference_link`. Check for existing memories first — **update rather than duplicate**.
- `memory_delete`: Remove memories that are no longer accurate. Update memories that turn out to be wrong or outdated.
- `memory_consolidate`: Run cleanup to merge duplicates and prune stale memories.

### Staleness
Memories marked as "stale" (older than 30 days) should be verified against the current state before acting on them. If a recalled memory conflicts with what you observe now, trust the current observation — and update or delete the stale memory.

### Ignore Memory
If the user says to **ignore** or **forget** something, do not reference those memories. Proceed as if they were never stored.

### Before Recommending from Memory
A memory is a point-in-time observation. Before recommending it:
- If the memory names a file path: verify the file still exists
- If the memory names a function or flag: search for it
- If the user is about to act on your recommendation, verify first
"The memory says X exists" is not the same as "X exists now."

Do NOT use `/memories/` file paths for storing memories. Use only the memory tools above.
"""
