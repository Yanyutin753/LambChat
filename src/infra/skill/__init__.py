"""
Skills 管理模块 - 简化架构
"""

from src.infra.skill.loader import load_skill_files
from src.infra.skill.manager import SkillManager
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.middleware import SkillsMiddleware
from src.infra.skill.storage import SkillStorage

__all__ = [
    "SkillManager",
    "SkillsMiddleware",
    "SkillStorage",
    "MarketplaceStorage",
    "load_skill_files",
]


async def init_skill_indexes() -> None:
    """初始化索引（应用启动时调用一次）"""
    storage = SkillStorage()
    marketplace = MarketplaceStorage()

    await storage.ensure_indexes()
    await marketplace.ensure_indexes()

    await storage.close()
    await marketplace.close()
