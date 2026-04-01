"""
Fast Agent 系统提示 - 简洁高效
"""

from src.agents.core.subagent_prompts import SUBAGENT_TASK_GUIDE, WORKFLOW_SECTION

FAST_SYSTEM_PROMPT = """You are an intelligent assistant with tools and skills.

## File System
| Path | Purpose |
|------|---------|
| `/workspace` | Persistent files |
| `/skills/` | Skill definitions (read-only) |

Cross-session memory: `memory_retain`, `memory_recall`, `memory_delete`."""

FAST_SYSTEM_PROMPT = FAST_SYSTEM_PROMPT + WORKFLOW_SECTION + SUBAGENT_TASK_GUIDE

DEFERRED_TOOL_GUIDE = ""
