"""记忆索引注入的缓存上界与 2s 硬超时（issue #278 补测）。"""

from __future__ import annotations

import asyncio
import time

import pytest

from src.infra.agent.middleware import prompt_injection as pi


@pytest.fixture(autouse=True)
def _clear_snapshot_caches():
    """模块级 dict 是共享状态——测试前后都清，防跨文件状态泄漏。"""
    pi._MEMORY_INDEX_SNAPSHOTS.clear()
    pi._MEMORY_INDEX_USER_SNAPSHOTS.clear()
    yield
    pi._MEMORY_INDEX_SNAPSHOTS.clear()
    pi._MEMORY_INDEX_USER_SNAPSHOTS.clear()


def test_user_snapshot_cache_bounded():
    cap = pi._MEMORY_INDEX_USER_SNAPSHOT_MAX_SIZE
    now = time.monotonic()
    for i in range(cap + 500):
        pi._MEMORY_INDEX_USER_SNAPSHOTS[f"u{i}"] = (now - i, "idx")
    pi._evict_oldest_user_snapshots()
    assert len(pi._MEMORY_INDEX_USER_SNAPSHOTS) <= cap


def test_user_snapshot_eviction_prefers_expired():
    cap = pi._MEMORY_INDEX_USER_SNAPSHOT_MAX_SIZE
    now = time.monotonic()
    for i in range(cap + 500):
        pi._MEMORY_INDEX_USER_SNAPSHOTS[f"stale-{i}"] = (now - 3600, "idx")
    pi._MEMORY_INDEX_USER_SNAPSHOTS["fresh"] = (now, "idx")
    pi._evict_oldest_user_snapshots()
    assert "fresh" in pi._MEMORY_INDEX_USER_SNAPSHOTS


@pytest.mark.asyncio
async def test_build_memory_index_times_out_to_empty(monkeypatch):
    async def slow(_uid):
        await asyncio.sleep(30)
        return "should never appear"

    monkeypatch.setattr(pi, "_build_memory_index_full", slow)
    t0 = time.monotonic()
    result = await pi._build_memory_index_for_user("u-timeout", session_id="s1")
    assert result == ""
    assert time.monotonic() - t0 < 5  # 远小于 30s，说明 2s 超时生效
