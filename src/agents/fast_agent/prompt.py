"""
Fast Agent 系统提示 - 简洁高效

角色身份通过 SectionPromptMiddleware 独立注入（见 persona.py），
基础提示词只包含能力描述，保证全局 KV 缓存稳定。
"""

from src.agents.core.prompt_policy import PERSISTENT_STORAGE_POLICY

FAST_SYSTEM_PROMPT = PERSISTENT_STORAGE_POLICY

DEFERRED_TOOL_GUIDE = ""
