"""用户级记忆开关（默认开启，存 users.metadata.memoryEnabled）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.infra.memory import user_pref


class _FakeUserCollection:
    def __init__(self, docs: dict[str, dict]):
        self._docs = docs

    async def find_one(self, query, _projection=None):
        key = query.get("_id")
        return self._docs.get(str(key))


@pytest.fixture(autouse=True)
def _clear_cache():
    user_pref._pref_cache.clear()
    yield
    user_pref._pref_cache.clear()


@pytest.mark.asyncio
async def test_absent_metadata_defaults_enabled(monkeypatch):
    monkeypatch.setattr(user_pref, "_get_users_collection", lambda: _FakeUserCollection({}))
    assert await user_pref.user_memory_enabled("u1") is True


@pytest.mark.asyncio
async def test_explicit_false_disables(monkeypatch):
    monkeypatch.setattr(
        user_pref,
        "_get_users_collection",
        lambda: _FakeUserCollection({"u1": {"metadata": {"memoryEnabled": False}}}),
    )
    assert await user_pref.user_memory_enabled("u1") is False


@pytest.mark.asyncio
async def test_explicit_true_enables(monkeypatch):
    monkeypatch.setattr(
        user_pref,
        "_get_users_collection",
        lambda: _FakeUserCollection({"u1": {"metadata": {"memoryEnabled": True}}}),
    )
    assert await user_pref.user_memory_enabled("u1") is True


@pytest.mark.asyncio
async def test_cache_hits_ttl(monkeypatch):
    calls = {"n": 0}

    def _coll():
        calls["n"] += 1
        return _FakeUserCollection({"u1": {"metadata": {"memoryEnabled": False}}})

    monkeypatch.setattr(user_pref, "_get_users_collection", _coll)
    assert await user_pref.user_memory_enabled("u1") is False
    assert await user_pref.user_memory_enabled("u1") is False
    assert calls["n"] == 1  # 第二次走缓存

    # 过期后重查
    stale = datetime.now(timezone.utc) - timedelta(seconds=user_pref.PREF_CACHE_TTL_SECONDS + 5)
    user_pref._pref_cache["u1"] = (stale, False)
    assert await user_pref.user_memory_enabled("u1") is False
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_storage_error_defaults_enabled(monkeypatch):
    def _boom():
        raise RuntimeError("mongo down")

    monkeypatch.setattr(user_pref, "_get_users_collection", _boom)
    assert await user_pref.user_memory_enabled("u1") is True  # fail-open


# ---------------------------------------------------------------------------
# 门控接线测试
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_recall_tool_gated_for_disabled_user(monkeypatch):
    from src.infra.memory import tools as memory_tools

    async def _disabled(uid):
        return False

    monkeypatch.setattr(memory_tools, "user_memory_enabled", _disabled)
    monkeypatch.setattr(memory_tools, "get_user_id_from_runtime", lambda _rt: "u1")

    class NoBackend:
        calls: list = []

        async def recall(self, *a, **k):
            NoBackend.calls.append(a)
            return {}

    async def fake_get_backend():
        return NoBackend()

    monkeypatch.setattr(memory_tools, "_get_backend", fake_get_backend)

    result = await memory_tools.memory_recall.ainvoke({"query": "测试"}, config={})
    import json

    parsed = json.loads(result) if isinstance(result, str) else result
    assert parsed.get("error") == "memory_disabled_for_user"
    assert NoBackend.calls == []


@pytest.mark.asyncio
async def test_append_memory_context_gated_for_disabled_user(monkeypatch):
    from src.infra.chat import memory_context

    monkeypatch.setattr(memory_context.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(memory_context.settings, "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED", True)

    async def _async_false(_uid):
        return False

    monkeypatch.setattr(user_pref, "user_memory_enabled", _async_false)

    called = []

    async def fake_recall(uid, query):
        called.append(query)
        return []

    monkeypatch.setattr(memory_context, "_recall_memories_raw", fake_recall)

    out = await memory_context.append_memory_context("足够长的一条消息内容", "u1")
    assert out == "足够长的一条消息内容"
    assert called == []


@pytest.mark.asyncio
async def test_auto_capture_gated_for_disabled_user(monkeypatch):
    from src.infra.memory import tools as memory_tools

    async def _disabled(uid):
        return False

    monkeypatch.setattr(memory_tools, "user_memory_enabled", _disabled)
    events: list = []

    async def fake_acquire(uid, iid):
        events.append("acquire")
        return "acquired"

    async def fake_release(uid, iid):
        events.append("release")

    monkeypatch.setattr(
        memory_tools, "_get_auto_capture_lock_fns", lambda: (fake_acquire, fake_release)
    )

    await memory_tools._auto_retain_user_memory("u1", "一条不该被评估的消息")

    assert events == []  # 关闭用户直接短路，连分布式锁都不碰


@pytest.mark.asyncio
async def test_pref_cache_bounded_under_burst(monkeypatch):
    """缓存上界：超限时先清过期再淘汰最旧，条目数不超过上限。"""
    cap = getattr(user_pref, "_PREF_CACHE_MAX_SIZE", None)
    if cap is None:
        cap = 2000
    stale = datetime.now(timezone.utc) - timedelta(seconds=9999)
    for i in range(cap + 500):
        user_pref._pref_cache[f"old-{i}"] = (stale, True)

    monkeypatch.setattr(user_pref, "_get_users_collection", lambda: _FakeUserCollection({}))
    await user_pref.user_memory_enabled("fresh-user")

    assert len(user_pref._pref_cache) <= cap
    assert "fresh-user" in user_pref._pref_cache
