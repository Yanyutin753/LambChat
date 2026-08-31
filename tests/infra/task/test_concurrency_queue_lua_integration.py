from __future__ import annotations

"""队列 Lua 脚本对真实 Redis 的语义验证（本地 / CI services.redis 真跑）。

接线测试（test_concurrency_queue.py）只验证 Python 侧传参；这里把三个脚本
（remove / mark-ready / position）发到真实 Redis 执行，验证 cjson 解析、
顺序保持、损坏条目容错与返回值编码这些 Lua 侧语义。Redis 不可达时自动跳过。
"""

import json
import uuid

import pytest

from src.infra.task.concurrency import (
    _QUEUE_MARK_READY_LUA,
    _QUEUE_POSITION_LUA,
    _QUEUE_REMOVE_LUA,
    UserConcurrencyLimiter,
)
from src.kernel.config import settings


@pytest.fixture
async def real_redis():
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.ping()
    except Exception:  # pragma: no cover - 环境无 Redis 时跳过
        pytest.skip("Redis 不可达，跳过队列 Lua 集成测试")
    yield client
    await client.aclose()


def _queue_key() -> str:
    return f"chat:queue:lua-test:{uuid.uuid4().hex}"


def _entry(run_id: str, session_id: str, **extra) -> str:
    return json.dumps({"run_id": run_id, "session_id": session_id, **extra})


async def test_remove_script_removes_matches_and_keeps_order(real_redis) -> None:
    key = _queue_key()
    entries = [
        _entry("run-1", "keep"),
        _entry("run-2", "remove"),
        "not-json-corrupt-entry",
        _entry("run-3", "keep"),
    ]
    await real_redis.rpush(key, *entries)
    try:
        result = await real_redis.eval(_QUEUE_REMOVE_LUA, 1, key, "session_id", "remove")

        payload = json.loads(result)
        assert payload["removed"] == 1
        assert payload["run_ids"] == ["run-2"]
        # 损坏条目（非 JSON）被保留，顺序不变
        remaining = await real_redis.lrange(key, 0, -1)
        assert remaining == [entries[0], entries[2], entries[3]]

        # 无匹配时返回整数 0，队列不动
        assert await real_redis.eval(_QUEUE_REMOVE_LUA, 1, key, "session_id", "absent") == 0
    finally:
        await real_redis.delete(key)


async def test_remove_script_deletes_queue_when_everything_matches(real_redis) -> None:
    key = _queue_key()
    await real_redis.rpush(key, _entry("run-1", "same"), _entry("run-2", "same"))
    try:
        result = await real_redis.eval(_QUEUE_REMOVE_LUA, 1, key, "session_id", "same")
        payload = json.loads(result)
        assert payload["removed"] == 2
        assert await real_redis.exists(key) == 0
    finally:
        await real_redis.delete(key)


async def test_mark_ready_script_flips_nested_task_context(real_redis) -> None:
    key = _queue_key()
    await real_redis.rpush(
        key,
        _entry("run-1", "session-1", task_context={"persisted": True}),
        _entry("run-2", "session-1"),
    )
    try:
        assert await real_redis.eval(_QUEUE_MARK_READY_LUA, 1, key, "run-2") == 1

        first, second = await real_redis.lrange(key, 0, -1)
        assert json.loads(first)["task_context"] == {"persisted": True}
        assert json.loads(second)["task_context"]["queue_ready"] is True

        # 不存在的 run 幂等返回 0
        assert await real_redis.eval(_QUEUE_MARK_READY_LUA, 1, key, "run-missing") == 0
    finally:
        await real_redis.delete(key)


async def test_position_script_returns_one_based_index(real_redis) -> None:
    key = _queue_key()
    await real_redis.rpush(
        key,
        _entry("run-1", "session-1"),
        _entry("run-2", "session-1"),
    )
    try:
        assert await real_redis.eval(_QUEUE_POSITION_LUA, 1, key, "run-1") == 1
        assert await real_redis.eval(_QUEUE_POSITION_LUA, 1, key, "run-2") == 2
        assert await real_redis.eval(_QUEUE_POSITION_LUA, 1, key, "run-missing") == 0
    finally:
        await real_redis.delete(key)


async def test_limiter_methods_against_real_redis(real_redis) -> None:
    """limiter 方法端到端（eval + 返回值解码）跑在真实 Redis 上。"""
    limiter = UserConcurrencyLimiter()
    limiter._redis = real_redis
    user_id = f"lua-test-{uuid.uuid4().hex}"
    key = limiter._queue_key(user_id)
    await real_redis.rpush(
        key,
        _entry("run-a", "session-x"),
        _entry("run-b", "session-y"),
    )
    try:
        assert await limiter.get_queue_position(user_id, "run-b") == 2
        assert await limiter.remove_queued_run(user_id, "run-a") == 1
        assert await limiter.get_queue_position(user_id, "run-b") == 1
    finally:
        await real_redis.delete(key)
