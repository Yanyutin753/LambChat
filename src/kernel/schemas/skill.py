"""
Skill schemas - 简化版（保留向后兼容）

新架构使用 src/infra/skill/types.py 中的类型，此文件仅保留最小化兼容定义。
"""

from enum import Enum


# Skill source type
class SkillSource(str, Enum):
    BUILTIN = "builtin"
    GITHUB = "github"
    MANUAL = "manual"
