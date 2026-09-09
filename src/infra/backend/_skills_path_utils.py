"""
Path utilities and storage cache for SkillsStoreBackend.

Contains:
- Regex patterns for skills paths
- Path normalization and parsing
- Global SkillStorage cache
- Async runner for sync wrappers
"""

import asyncio
import re

from src.infra.async_utils import loop_bridge
from src.infra.logging import get_logger
from src.infra.skill.storage import SkillStorage

logger = get_logger(__name__)

SKILLS_PATH_PATTERN = re.compile(r"^/skills/([^/]+)/(.+)$")
SKILLS_ROOT_PATTERN = re.compile(r"^/skills/?$")
SKILLS_DIR_PATTERN = re.compile(r"^/skills/([^/]+)/?$")

SKILL_NAME_PATTERN = re.compile(r"^[\w一-鿿\-.]+$")

_storage_cache: dict[str, SkillStorage] = {}
_storage_lock = asyncio.Lock()
MAX_STORAGE_CACHE_SIZE = 1000


async def _get_cached_storage(user_id: str) -> SkillStorage:
    """获取缓存的 SkillStorage 实例（async-safe，带容量上限）"""
    async with _storage_lock:
        if user_id not in _storage_cache:
            if len(_storage_cache) >= MAX_STORAGE_CACHE_SIZE:
                _storage_cache.pop(next(iter(_storage_cache)))
            _storage_cache[user_id] = SkillStorage()
        return _storage_cache[user_id]


def _run_async(coro):
    """
    在同步上下文中安全地运行异步协程。

    如果没有运行中的事件循环 → 经 loop_bridge 投递到已登记的进程主循环
    （API lifespan / arq worker 启动时登记），未登记时退回 asyncio.run()；
    如果已有运行中的事件循环 → 报错，要求调用方使用异步 API。

    背景（生产事故 2026-09-09，会话 7ffcfc36）：同步包装经 asyncio.run 在
    blocking-io 线程里临时建循环执行协程，而全局缓存的 SkillStorage（Motor）
    绑定 worker 主循环——跨循环复用报 ``got Future attached to a different
    loop``，transfer_path 下载 fallback 直接失败、文件被静默跳过。统一投递到
    主循环后共享存储全部收敛到同一循环。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        coro.close()
        raise RuntimeError(
            "SkillsStoreBackend synchronous API cannot run inside an active event loop; "
            "use the async backend methods instead."
        )

    return loop_bridge.run_coro_sync(coro)


def normalize_path(path: str) -> str:
    """标准化路径，确保始终以 /skills/ 开头"""
    if not path:
        return "/skills/"

    if path == "/skills":
        return "/skills/"

    if path.startswith("/skills/"):
        return path

    if path.startswith("skills/"):
        return f"/{path}"

    if path.startswith("/"):
        return f"/skills{path}"

    return f"/skills/{path}"


def parse_skill_path(path: str):
    """
    解析 skills 路径

    Returns:
        (skill_name, file_path) 或 None（如果路径无效）
    """
    match = SKILLS_PATH_PATTERN.match(path)
    if match:
        return match.group(1), match.group(2)
    return None


def is_skills_root(path: str) -> bool:
    """检查是否是 skills 根路径"""
    normalized = normalize_path(path)
    return normalized in ("/skills/", "/skills") or bool(SKILLS_ROOT_PATTERN.match(normalized))


def is_skill_dir(path: str) -> bool:
    """检查是否是某个 skill 的目录"""
    normalized = normalize_path(path)
    return bool(SKILLS_DIR_PATTERN.match(normalized))


def get_skill_name_from_dir(path: str) -> str | None:
    """从目录路径获取 skill 名称"""
    normalized = normalize_path(path)
    match = SKILLS_DIR_PATTERN.match(normalized)
    if match:
        return match.group(1)
    return None
