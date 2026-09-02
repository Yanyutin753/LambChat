"""自进化记忆——定时调度（APScheduler，多副本需 Redis 扫描锁）。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from src.kernel.config import settings

logger = logging.getLogger(__name__)

EVOLUTION_INTERVAL_SECONDS = 12 * 3600
MAX_USERS_PER_RUN = 50
EVOLUTION_SCAN_LOCK_KEY = "memory:evolution_scan_lock"
EVOLUTION_SCAN_LOCK_TTL = 600  # 10 分钟（远小于调度间隔，防死锁）


_RELEASE_LOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('del', KEYS[1]) else return 0 end"
)

_REFRESH_LOCK_LUA = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then "
    "return redis.call('expire', KEYS[1], ARGV[2]) else return 0 end"
)


async def _acquire_scan_lock() -> Optional[str]:
    """Redis SETNX 扫描锁——多副本防重。fail-closed：Redis 不可用时不执行。

    返回本次持有的 token（释放用）；未取到锁返回 None。
    token 由调用方持有，防止锁 TTL 过期交叉后释放掉其他副本的锁。
    """
    try:
        from src.infra.storage.redis import get_redis_client

        token = uuid.uuid4().hex[:8]
        acquired = await get_redis_client().set(
            EVOLUTION_SCAN_LOCK_KEY, token, nx=True, ex=EVOLUTION_SCAN_LOCK_TTL
        )
        return token if acquired else None
    except Exception as e:
        logger.warning("[MemoryEvolution] scan lock failed (fail-closed): %s", e)
        return None


async def _release_scan_lock(token: str) -> None:
    """Token-checked 释放——只删自己的锁。"""
    if not token:
        return
    try:
        from src.infra.storage.redis import get_redis_client

        await get_redis_client().eval(  # type: ignore[misc]
            _RELEASE_LOCK_LUA, 1, EVOLUTION_SCAN_LOCK_KEY, token
        )
    except Exception:
        pass


async def _refresh_scan_lock(token: str) -> bool:
    """Token-checked TTL 续期——单轮扫描最坏可跑远超锁 TTL（50 用户 × 多次
    反思 LLM 调用），运行中逐用户续期防止锁过期后被其他副本并发抢占。

    返回 False 仅当 Redis 明确表示锁已易主（调用方应立即中止扫描）；
    Redis 故障时 fail-open 返回 True——无法证伪所有权，不误杀进行中的长任务。
    """
    if not token:
        return False
    try:
        from src.infra.storage.redis import get_redis_client

        result: Any = await get_redis_client().eval(  # type: ignore[misc]
            _REFRESH_LOCK_LUA, 1, EVOLUTION_SCAN_LOCK_KEY, token, str(EVOLUTION_SCAN_LOCK_TTL)
        )
        return bool(int(result))
    except Exception as e:
        logger.warning("[MemoryEvolution] scan lock refresh failed (fail-open): %s", e)
        return True


async def _collect_signal_user_ids(cutoff: datetime) -> list[str]:
    """聚合扫描有信号的用户，按最老信号优先，去重限次。"""
    from src.infra.memory.evolution.reflector import (
        _get_feedback_collection,
        _get_traces_collection,
    )

    pipeline = [
        {
            "$match": {
                "rating": "down",
                "created_at": {"$gte": cutoff},
                "user_id": {"$exists": True},
            }
        },
        {"$group": {"_id": "$user_id", "oldest": {"$min": "$created_at"}}},
        {"$sort": {"oldest": 1}},
        {"$limit": MAX_USERS_PER_RUN},
        {"$project": {"_id": 0, "user_id": "$_id"}},
    ]
    users: list[str] = []
    try:
        async for d in _get_feedback_collection().aggregate(pipeline):
            uid = d.get("user_id")
            if uid:
                users.append(str(uid))
    except Exception as e:
        logger.warning("[MemoryEvolution] feedback user scan failed: %s", e)

    if len(users) < MAX_USERS_PER_RUN:
        try:
            seen = set(users)
            async for d in (
                _get_traces_collection()
                .find(
                    {
                        # traces 终态写入 "error"；"failed" 仅防御性兼容
                        "status": {"$in": ["error", "failed"]},
                        "started_at": {"$gte": cutoff},
                        "user_id": {"$exists": True},
                    },
                    {"user_id": 1},
                )
                .limit(MAX_USERS_PER_RUN * 2)
            ):
                uid = str(d.get("user_id") or "")
                if uid and uid not in seen:
                    users.append(uid)
                    seen.add(uid)
                    if len(users) >= MAX_USERS_PER_RUN:
                        break
        except Exception as e:
            logger.warning("[MemoryEvolution] trace user scan failed: %s", e)

    return users[:MAX_USERS_PER_RUN]


async def run_scheduled_evolution() -> dict:
    """定时执行：取 Redis 扫描锁 → 扫有信号的用户 → 逐个进化。"""
    if not getattr(settings, "ENABLE_MEMORY", False):
        return {"skipped": "memory_disabled"}
    if not getattr(settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", False):
        return {"skipped": "self_evolve_disabled"}

    lock_token = await _acquire_scan_lock()
    if not lock_token:
        logger.info("[MemoryEvolution] scan lock held by another instance, skipping")
        return {"skipped": "scan_lock_not_acquired"}

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        user_ids = await _collect_signal_user_ids(cutoff)
        if not user_ids:
            return {"users": 0, "stored": 0}

        from src.infra.memory.tools import _get_backend

        backend = await _get_backend()
        if backend is None:
            return {"skipped": "no_backend"}

        from src.infra.memory.evolution.reflector import evolve_user

        total = 0
        users_processed = 0
        for uid in user_ids:
            if not await _refresh_scan_lock(lock_token):
                logger.warning(
                    "[MemoryEvolution] scan lock lost mid-scan (users_done=%d), aborting",
                    users_processed,
                )
                return {"skipped": "scan_lock_lost"}
            try:
                r = await evolve_user(backend, uid)
                stored = int(r.get("stored") or 0)
                total += stored
                if stored > 0:
                    users_processed += 1
            except Exception as e:
                logger.warning("[MemoryEvolution] evolve failed for %s: %s", uid, e)
        logger.info(
            "[MemoryEvolution] scheduled run: users_with_signals=%d users_evolved=%d stored=%d",
            len(user_ids),
            users_processed,
            total,
        )
        return {"users": len(user_ids), "users_evolved": users_processed, "stored": total}
    finally:
        await _release_scan_lock(lock_token)


def is_evolution_enabled() -> bool:
    return bool(getattr(settings, "ENABLE_MEMORY", False)) and bool(
        getattr(settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", False)
    )
