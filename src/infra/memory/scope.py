"""记忆作用域（scope）——归属边界的单一事实源。

scope 回答"这条记忆属于谁"（user / project / reference），与 `context` 的
内容分类语义分离。项目归属永远来自可靠来源（显式参数或会话元数据），
写入侧不做任何猜测；拿不到 project_id 的项目类内容降级为 user scope。

设计文档：docs/superpowers/specs/2026-09-04-memory-scope-and-context-design.md
"""

from __future__ import annotations

import time
from typing import Any, Optional

from src.infra.logging import get_logger

logger = get_logger(__name__)

MEMORY_SCOPES = ("user", "project", "reference")

# 会话 → 项目解析的进程内缓存 TTL（含负缓存）。索引快照本身 30 分钟，
# 60s 的归属可见性延迟可接受；会话中途改派项目最多一分钟内跟进。
_SESSION_PROJECT_TTL_SECONDS = 60.0
_SESSION_PROJECT_CACHE_MAX_SIZE = 4096

_SESSION_PROJECT_CACHE: dict[str, tuple[float, Optional[str]]] = {}


class ScopeResolutionError(ValueError):
    """retain 的 scope 参数无法解析为合法归属。"""


def resolve_retain_scope(
    *,
    scope: Optional[str],
    project_id: Optional[str],
) -> tuple[str, Optional[str]]:
    """推导写入时的 (scope, project_id)。

    - 非法 scope / scope=project 无 project_id → ScopeResolutionError
    - 归属只认 project_id：显式 project_id（无 scope）→ project；
      拿不到 project_id 的项目类内容降级 user（不猜归属，context 不参与）
    - 非 project scope 一律清空 project_id
    """
    if scope is not None and scope not in MEMORY_SCOPES:
        raise ScopeResolutionError(
            f"Invalid scope '{scope}'; expected one of {', '.join(MEMORY_SCOPES)}"
        )
    pid = (project_id or "").strip() or None
    if scope == "project" and pid is None:
        raise ScopeResolutionError(
            "scope='project' requires a project_id (no project context on this session)"
        )
    if scope is None:
        scope = "project" if pid is not None else "user"
    if scope != "project":
        pid = None
    return scope, pid


def build_dedup_scope_clause(scope: str, project_id: Optional[str]) -> dict[str, Any]:
    """写入侧语义/摘要去重的候选边界。

    project 记忆只在同一 (scope, project_id) 内匹配——跨项目绝不合并；
    user/reference 记忆的候选含 legacy 无 scope 文档（视同 user）。
    """
    if scope == "project":
        return {"scope": "project", "project_id": project_id}
    return {"scope": {"$in": [scope, None]}}


def _get_sessions_collection():
    from src.infra.storage.mongodb import get_mongo_client
    from src.kernel.config import settings

    client = get_mongo_client()
    return client[settings.MONGODB_DB][settings.MONGODB_SESSIONS_COLLECTION]


async def resolve_session_project_id(session_id: Optional[str]) -> Optional[str]:
    """反查会话归属项目（sessions.metadata.project_id），带 TTL 缓存与降级。

    任何失败 → None（按无项目行为继续），绝不阻塞调用方。
    """
    if not session_id:
        return None
    now = time.monotonic()
    cached = _SESSION_PROJECT_CACHE.get(session_id)
    if cached is not None and (now - cached[0]) < _SESSION_PROJECT_TTL_SECONDS:
        return cached[1]

    project_id: Optional[str] = None
    try:
        doc = await _get_sessions_collection().find_one(
            {"session_id": session_id}, {"metadata.project_id": 1}
        )
        metadata = (doc or {}).get("metadata") or {}
        project_id = str(metadata.get("project_id") or "").strip() or None
    except Exception as exc:
        logger.debug(
            "[MemoryScope] session project lookup failed for %s: %s",
            session_id,
            type(exc).__name__,
        )
        project_id = None

    if len(_SESSION_PROJECT_CACHE) >= _SESSION_PROJECT_CACHE_MAX_SIZE:
        _SESSION_PROJECT_CACHE.clear()
    _SESSION_PROJECT_CACHE[session_id] = (now, project_id)
    return project_id
