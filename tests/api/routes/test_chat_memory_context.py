"""chat.py 模型侧消息装配（写时注入链）测试（A1）。

断言两件事：
1. 记忆块追加在模型侧消息（会持久化、随请求发送），display 始终用原始消息；
2. 注入是写时一次性、确定性的——持久化历史与发送字节一致，前缀缓存连续。
"""

from __future__ import annotations

import pytest

from src.infra.chat import memory_context
from src.infra.chat.model_facing import build_model_facing_message
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


@pytest.mark.asyncio
async def test_model_facing_message_skips_memory_when_deferred(
    monkeypatch: pytest.MonkeyPatch,
):
    """POST 关键路径不再做记忆注入（挪到 executor 后台）——include_memory=False
    时即使开关全开也不产生记忆块，提交延迟与召回解耦。"""
    monkeypatch.setattr(memory_context.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(memory_context.settings, "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED", True)

    async def _has_memories(user_id: str, query: str) -> list[dict]:
        return [_memory()]

    monkeypatch.setattr(memory_context, "_recall_memories_raw", _has_memories)

    message = await build_model_facing_message(
        raw_message="你好",
        user_timezone="Asia/Shanghai",
        enabled_skills=None,
        active_goal=None,
        auto_mode=False,
        user_id="u1",
        include_memory=False,
    )

    assert "<memory_context>" not in message


@pytest.mark.asyncio
async def test_execute_agent_stream_never_injects_memory(monkeypatch: pytest.MonkeyPatch):
    """Codex 式会话基线：注入只在 POST 首轮发生，executor 逐轮注入已移除
    （逐轮变化块是前缀缓存杀手——生产实测确认）。"""
    from src.api.routes import chat as chat_route

    captured = {}

    class FakeAgent:
        def stream(self, message, *a, **kw):
            captured["message"] = message

            async def gen():
                yield {"event": "thinking", "data": {"content": "ok"}}

            return gen()

    async def fake_get(_agent_id):
        return FakeAgent()

    monkeypatch.setattr("src.agents.core.AgentFactory.get", fake_get)

    class FakePresenter:
        run_id = "run-test"
        hitl_suspended = False

    events = []
    gen = chat_route._execute_agent_stream(
        session_id="s1",
        agent_id="fast_agent",
        message="base message",
        user_id="u1",
        presenter=FakePresenter(),
        recommendation_input="原始问题",
    )
    async for ev in gen:
        events.append(ev)

    assert all(ev.get("event") != "status" for ev in events)
    assert captured["message"] == "base message", "executor 必须原样透传消息"


@pytest.mark.asyncio
async def test_session_memory_baseline_only_first_turn(monkeypatch: pytest.MonkeyPatch):
    """会话首轮判定：无历史消息才注入记忆基线（append-only，之后轮次不再变）。"""
    from src.infra.chat.session_baseline import session_has_prior_messages
    from src.kernel.config import settings as kernel_settings

    monkeypatch.setattr(kernel_settings, "MONGODB_TRACES_COLLECTION", "traces")

    counts = {"called_with": [], "ret": 0}

    class FakeCol:
        async def count_documents(self, query):
            counts["called_with"].append(query)
            return counts["ret"]

    class FakeDB:
        def __getitem__(self, name):
            assert name == "traces", name
            return FakeCol()

    class FakeClient:
        def __getitem__(self, name):
            return FakeDB()

    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: FakeClient())

    assert await session_has_prior_messages("s1") is False  # count=0 → 首轮
    assert counts["called_with"] == [{"session_id": "s1"}]
    counts["ret"] = 3
    assert await session_has_prior_messages("s1") is True


@pytest.mark.asyncio
async def test_session_baseline_prepended_at_message_head(monkeypatch: pytest.MonkeyPatch):
    """Codex input[1]：记忆索引基线置于首条消息头部——稳定内容在时间戳等
    变化内容之前，同用户跨会话公共前缀延伸到索引末尾。"""
    from src.api.routes import chat as chat_route

    async def fake_baseline(user_id):
        return "<memory_index_context>\n- 记忆索引行\n</memory_index_context>"

    monkeypatch.setattr(
        "src.infra.agent.middleware.prompt_injection.build_session_memory_baseline",
        fake_baseline,
    )

    msg, _tc = await chat_route.assemble_first_turn_message(
        raw_message="你好",
        user_timezone="Asia/Shanghai",
        enabled_skills=None,
        active_goal=None,
        auto_mode=False,
        user_id="u1",
        include_memory=True,
        include_timestamp=True,
        last_tc_signature=None,
    )

    assert msg.startswith("<memory_index_context>")
    assert msg.index("<memory_index_context>") < msg.index("[User message sent at")


@pytest.mark.asyncio
async def test_turn_context_signature_dedup():
    """goal/自动模式块签名去重：目标未变的后续轮次不再注入。"""
    from src.infra.chat.session_baseline import _turn_context_signature
    from src.infra.goal import GoalSpec

    goal = GoalSpec(objective="写周报", rubric="完成即达标")
    assert _turn_context_signature(goal, False) == "写周报|auto=False"
    assert _turn_context_signature(None, True) == "|auto=True"
    assert _turn_context_signature(None, False) is None


def test_time_report_drift():
    """报时漂移：无记录=应报；刚报过=不报；超阈值=应报。"""
    from datetime import datetime, timedelta, timezone

    from src.infra.chat.session_baseline import TIME_REPORT_DRIFT_SECONDS, _time_report_due

    assert _time_report_due(None) is True
    assert _time_report_due({}) is True
    recent = datetime.now(timezone.utc).isoformat()
    assert _time_report_due({"prompt_time_reported_at": recent}) is False
    stale = (
        datetime.now(timezone.utc) - timedelta(seconds=TIME_REPORT_DRIFT_SECONDS + 60)
    ).isoformat()
    assert _time_report_due({"prompt_time_reported_at": stale}) is True
