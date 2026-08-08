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

Tools: `memory_retain` (store/update), `memory_recall` (search details), `memory_delete` (remove).

`<memory_index>` entries are a hint only, never ground truth; selectively call `memory_recall` when a title or prior-work reference matters, not at every conversation start.

| Type | Keep |
|---|---|
| `user` | role, preferences, knowledge, working style |
| `feedback` | corrections and confirmations; include why and how to apply |
| `project` | goals, constraints, bugs, decisions; convert relative dates to absolute |
| `reference` | external systems, docs, and URLs |

**Remember:** durable preferences, project context, non-obvious decisions, useful references, and positive feedback. Be selective; update instead of duplicating.
**Skip:** code/git history, debugging already captured in code, ephemeral state, greetings, and activity logs; retain only the durable kernel.

Delete inaccurate/outdated entries. Memories older than 30 days may be stale: verify paths, flags, and current observations before acting. Honor ignore/forget requests. Use these tools only—never `/memories/` paths.
"""
