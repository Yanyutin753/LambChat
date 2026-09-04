"""记忆索引注入的缓存上界与 2s 硬超时（issue #278 补测）。"""

from __future__ import annotations

import asyncio
import time
import unittest.mock as mock

import pytest
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool

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


def _tool(name: str, description: str) -> StructuredTool:
    def fn(query: str = "") -> str:
        return query

    return StructuredTool.from_function(fn, name=name, description=description)


@pytest.mark.asyncio
async def test_memory_recall_index_respects_dedicated_index_switch(monkeypatch):
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "NATIVE_MEMORY_INDEX_ENABLED", False)

    async def unexpected_index(*args, **kwargs):
        raise AssertionError("disabled index must not query memory storage")

    monkeypatch.setattr(pi, "_build_memory_index_for_user", unexpected_index)

    result = await pi.build_memory_recall_index_context("u1", session_id="s1")

    assert result == ""


@pytest.mark.asyncio
async def test_memory_index_middleware_attaches_index_only_to_recall_tool(monkeypatch):
    async def fake_index(
        user_id: str, *, session_id: str | None = None, project_id: str | None = None
    ) -> str:
        assert user_id == "u1"
        assert session_id == "s1"
        return "<memory_index>\n- 皮蛋供应商\n</memory_index>"

    monkeypatch.setattr(pi, "_build_memory_index_for_user", fake_index)
    middleware = pi.MemoryRecallIndexMiddleware(user_id="u1", session_id="s1")
    recall = _tool("memory_recall", "base recall description")
    other = _tool("other_tool", "other description")

    class FakeRequest:
        def __init__(self, tools, messages):
            self.tools = tools
            self.messages = messages

        def override(self, **updates):
            updated = FakeRequest(self.tools, self.messages)
            for key, value in updates.items():
                setattr(updated, key, value)
            return updated

    request = FakeRequest(
        [recall, other],
        [HumanMessage(content="曼玲粥的皮蛋供应商是谁？")],
    )
    captured = {}

    async def handler(updated):
        captured["request"] = updated
        return object()

    await middleware.awrap_model_call(request, handler)

    updated = captured["request"]
    recall_tool = next(tool for tool in updated.tools if tool.name == "memory_recall")
    other_tool = next(tool for tool in updated.tools if tool.name == "other_tool")
    assert "base recall description" in recall_tool.description
    assert "<memory_index>" in recall_tool.description
    assert "皮蛋供应商" in recall_tool.description
    assert other_tool.description == "other description"
    assert updated.messages[0].content == "曼玲粥的皮蛋供应商是谁？"
    assert "<memory_index" not in str(updated.messages[0].content)


@pytest.mark.asyncio
async def test_memory_index_middleware_is_stable_for_same_session(monkeypatch):
    calls = 0

    async def fake_index(
        user_id: str, *, session_id: str | None = None, project_id: str | None = None
    ) -> str:
        nonlocal calls
        calls += 1
        return "<memory_index>stable</memory_index>"

    monkeypatch.setattr(pi, "_build_memory_index_for_user", fake_index)
    middleware = pi.MemoryRecallIndexMiddleware(user_id="u1", session_id="s1")
    descriptions = []

    class FakeRequest:
        def __init__(self, tools):
            self.tools = tools

        def override(self, **updates):
            updated = FakeRequest(self.tools)
            for key, value in updates.items():
                setattr(updated, key, value)
            return updated

    for _ in range(2):
        request = FakeRequest([_tool("memory_recall", "base")])

        async def handler(updated):
            descriptions.append(updated.tools[0].description)
            return object()

        await middleware.awrap_model_call(request, handler)

    assert descriptions[0] == descriptions[1]
    assert calls == 1


@pytest.mark.asyncio
async def test_memory_write_does_not_break_current_session_snapshot():
    """中途写记忆只影响新会话：已加载的 middleware 实例（=当前会话）字节不变。"""

    class FakeRequest:
        def __init__(self, tools):
            self.tools = tools

        def override(self, **updates):
            updated = FakeRequest(self.tools)
            for key, value in updates.items():
                setattr(updated, key, value)
            return updated

    async def run_turn(middleware):
        request = FakeRequest([_tool("memory_recall", "base")])

        async def handler(updated):
            return updated.tools[0].description

        return await middleware.awrap_model_call(request, handler)

    async def fake_index_v1(
        user_id: str, *, session_id: str | None = None, project_id: str | None = None
    ) -> str:
        return "<memory_index>v1</memory_index>"

    async def fake_index_v2(
        user_id: str, *, session_id: str | None = None, project_id: str | None = None
    ) -> str:
        return "<memory_index>v2</memory_index>"

    with mock.patch.object(pi, "_build_memory_index_for_user", fake_index_v1):
        middleware = pi.MemoryRecallIndexMiddleware(user_id="u1", session_id="s-live")
        first = await run_turn(middleware)

    # 会话中途写入记忆 → 失效广播清空模块级快照 + 新数据
    pi._MEMORY_INDEX_SNAPSHOTS.clear()

    with mock.patch.object(pi, "_build_memory_index_for_user", fake_index_v2):
        # 同一会话的下一轮：middleware 已加载，索引字节不变（KV 前缀不击穿）
        second = await run_turn(middleware)
        # 新会话：拿到新版本（写入对新会话可见）
        fresh = await pi.build_memory_recall_index_context("u1", session_id="s-next")

    assert first == second
    assert "v1" in first
    assert "v2" in fresh


@pytest.mark.asyncio
async def test_middleware_resolves_project_once_per_session(monkeypatch):
    """project_id 在会话首构建时解析一次：后续轮次不再反查（字节稳定 + 省 Mongo）。"""
    from src.infra.memory import scope as scope_module

    resolve_calls: list[str | None] = []

    async def fake_resolve(session_id):
        resolve_calls.append(session_id)
        return "proj-1"

    async def fake_index(
        user_id: str, *, session_id: str | None = None, project_id: str | None = None
    ) -> str:
        assert project_id == "proj-1"
        return "<memory_index>scoped</memory_index>"

    with mock.patch.object(scope_module, "resolve_session_project_id", fake_resolve):
        with mock.patch.object(pi, "_build_memory_index_for_user", fake_index):
            middleware = pi.MemoryRecallIndexMiddleware(user_id="u1", session_id="s1")

            class FakeRequest:
                def __init__(self, tools):
                    self.tools = tools

                def override(self, **updates):
                    updated = FakeRequest(self.tools)
                    for key, value in updates.items():
                        setattr(updated, key, value)
                    return updated

            for _ in range(3):
                request = FakeRequest([_tool("memory_recall", "base")])

                async def handler(updated):
                    return object()

                await middleware.awrap_model_call(request, handler)

    assert resolve_calls == ["s1"]
