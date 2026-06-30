"""
Fast Agent 系统提示 - 简洁高效

角色身份通过 SectionPromptMiddleware 独立注入（见 persona.py），
基础提示词只包含能力描述，保证全局 KV 缓存稳定。
"""

FAST_SYSTEM_PROMPT = """## File System
| Path | Purpose |
|------|---------|
| `/workflow/<session-id>` | Current session workflow files |
| `/skills/` | Skill definitions (editable) |

The default persistent file workspace is scoped by the current session id. Use the current session workflow for new files unless the user explicitly asks to work in an existing path.

Cross-session memory: `memory_retain`, `memory_recall`, `memory_delete`.
Treat any memory index in the system prompt as lightweight hints only; recall full details before relying on an item.

**Proactive memory retention:** Store durable user facts, reasoned preferences, constrained project details, and explicit feedback via `memory_retain`. Do NOT store greetings, questions, code, or ephemeral state."""

DEFERRED_TOOL_GUIDE = ""
