"""自进化记忆——夜间调度（arq 统一调度器）。"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from src.kernel.config import settings

logger = logging.getLogger(__name__)

EVOLUTION_INTERVAL_SECONDS = 12 * 3600
MAX_USERS_PER_RUN = 50


async def run_scheduled_evolution() -> dict:
    """扫窗口内有信号的用户，逐个跑进化（受双层开关与用户开关门控）。"""
    if not getattr(settings, "ENABLE_MEMORY", False):
        return {"skipped": "memory_disabled"}
    if not getattr(settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", False):
        return {"skipped": "self_evolve_disabled"}

    from src.infra.memory.evolution.reflector import (
        _get_feedback_collection,
        _get_traces_collection,
        evolve_user,
    )
    from src.infra.memory.tools import _get_backend

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    user_ids: set[str] = set()
    try:
        async for d in _get_feedback_collection().find(
            {"rating": "down", "created_at": {"$gte": cutoff}}, {"user_id": 1}
        ):
            if d.get("user_id"):
                user_ids.add(str(d["user_id"]))
    except Exception as e:
        logger.debug("[MemoryEvolution] feedback user scan failed: %s", e)
    try:
        async for d in (
            _get_traces_collection()
            .find({"status": "failed", "started_at": {"$gte": cutoff}}, {"user_id": 1})
            .limit(MAX_USERS_PER_RUN)
        ):
            if d.get("user_id"):
                user_ids.add(str(d["user_id"]))
    except Exception as e:
        logger.debug("[MemoryEvolution] trace user scan failed: %s", e)

    if not user_ids:
        return {"users": 0, "stored": 0}

    backend = await _get_backend()
    if backend is None:
        return {"skipped": "no_backend"}

    total = 0
    users = 0
    for uid in list(user_ids)[:MAX_USERS_PER_RUN]:
        try:
            r = await evolve_user(backend, uid)
            total += int(r.get("stored") or 0)
            users += 1
        except Exception as e:
            logger.warning("[MemoryEvolution] evolve failed for %s: %s", uid, e)
    logger.info("[MemoryEvolution] scheduled run: users=%d stored=%d", users, total)
    return {"users": users, "stored": total}


def is_evolution_enabled() -> bool:
    return bool(getattr(settings, "ENABLE_MEMORY", False)) and bool(
        getattr(settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", False)
    )
