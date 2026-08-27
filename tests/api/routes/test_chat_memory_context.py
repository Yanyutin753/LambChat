"""chat.py 模型侧消息装配（写时注入链）测试（A1）。

断言两件事：
1. 记忆块追加在模型侧消息（会持久化、随请求发送），display 始终用原始消息；
2. 注入是写时一次性、确定性的——持久化历史与发送字节一致，前缀缓存连续。
"""

from __future__ import annotations

import pytest

from src.api.routes.chat import build_model_facing_message
from src.infra.chat import memory_context
from src.kernel.schemas.agent import GoalSpec


def _memory(**overrides) -> dict:
    base = {
        "memory_id": "m1",
        "type": "user",
        "title": "偏好中文回复",
        "summary": "用户偏好中文交流",
        "created_at": "2026-08-20T10:00:00+00:00",
        "source": "manual",
    }
    base.update(overrides)
    return base


async def _no_memories(user_id: str, query: str) -> list[dict]:
    return []


@pytest.mark.asyncio
async def test_model_facing_message_matches_legacy_chain_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(memory_context.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(memory_context.settings, "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED", True)
    monkeypatch.setattr(memory_context, "_recall_memories_raw", _no_memories)

    message = await build_model_facing_message(
        raw_message="你好",
        user_timezone="Asia/Shanghai",
        enabled_skills=None,
        active_goal=None,
        auto_mode=False,
        user_id="u1",
    )

    assert message.startswith("[User message sent at:")
    assert message.rstrip().endswith("你好")
    assert "<memory_context>" not in message


@pytest.mark.asyncio
async def test_memory_block_appended_at_tail_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(memory_context.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(memory_context.settings, "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED", True)
    seen = {}

    async def fake_recall(user_id: str, query: str) -> list[dict]:
        seen["args"] = (user_id, query)
        return [_memory()]

    monkeypatch.setattr(memory_context, "_recall_memories_raw", fake_recall)

    message = await build_model_facing_message(
        raw_message="帮我总结项目进度",
        user_timezone="Asia/Shanghai",
        enabled_skills=None,
        active_goal=None,
        auto_mode=False,
        user_id="u1",
    )

    assert seen["args"][0] == "u1"
    assert seen["args"][1] == "帮我总结项目进度"  # 检索用原始消息，不用带时间戳文本
    assert "<memory_context>" in message
    assert message.endswith("</memory_context>")  # 块在消息尾部——前缀缓存安全位置
    assert "偏好中文回复" in message


@pytest.mark.asyncio
async def test_goal_and_memory_coexist(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(memory_context.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(memory_context.settings, "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED", True)

    async def fake_recall(user_id: str, query: str) -> list[dict]:
        return [_memory()]

    monkeypatch.setattr(memory_context, "_recall_memories_raw", fake_recall)

    message = await build_model_facing_message(
        raw_message="继续把文档写完",
        user_timezone=None,
        enabled_skills=None,
        active_goal=GoalSpec(objective="finish docs", rubric="- docs done"),
        auto_mode=False,
        user_id="u1",
    )

    assert "finish docs" in message  # turn_context 仍在
    assert message.endswith("</memory_context>")  # 记忆块在最后


@pytest.mark.asyncio
async def test_recall_failure_leaves_message_intact(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(memory_context.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(memory_context.settings, "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED", True)

    async def broken_recall(user_id: str, query: str) -> list[dict]:
        raise RuntimeError("backend down")

    monkeypatch.setattr(memory_context, "_recall_memories_raw", broken_recall)

    message = await build_model_facing_message(
        raw_message="你好",
        user_timezone=None,
        enabled_skills=None,
        active_goal=None,
        auto_mode=False,
        user_id="u1",
    )

    assert message.endswith("你好")
    assert "<memory_context>" not in message
