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


def _fake_agent_factory(captured: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    """FakeAgent：捕获 executor 实际喂给 agent.stream 的最终消息。"""

    class FakeAgent:
        def stream(self, message, *a, **kw):
            captured["message"] = message

            async def gen():
                yield {"event": "thinking", "data": {"content": "ok"}}

            return gen()

    async def fake_get(_agent_id):
        return FakeAgent()

    monkeypatch.setattr("src.agents.core.AgentFactory.get", fake_get)


class _FakePresenter:
    run_id = "run-test"
    hitl_suspended = False


@pytest.mark.asyncio
async def test_execute_agent_stream_emits_status_then_injects_first_round_memory(
    monkeypatch: pytest.MonkeyPatch,
):
    """首轮记忆装配移回 executor 后台：先发 status{stage:memory} 让前端出
    加载行（沙箱初始化式），注入完成才开跑 agent——提交延迟与召回解耦。"""
    from src.api.routes import chat as chat_route

    captured = {}
    _fake_agent_factory(captured, monkeypatch)

    async def fake_first_round(session_id, *, exclude_run_id=None):
        return True

    monkeypatch.setattr(chat_route, "_should_inject_session_memory", fake_first_round)

    injected = {}

    async def fake_inject(message: str, *, user_id: str, raw_query: str | None) -> str:
        injected["args"] = (user_id, raw_query)
        return f"{message}\n\n<memory_context>注入块</memory_context>"

    monkeypatch.setattr(chat_route, "inject_session_memory", fake_inject)

    events = []
    gen = chat_route._execute_agent_stream(
        session_id="s1",
        agent_id="fast_agent",
        message="base message",
        user_id="u1",
        presenter=_FakePresenter(),
        recommendation_input="原始问题",
    )
    async for ev in gen:
        events.append(ev)

    assert events[0]["event"] == "status" and events[0]["data"]["stage"] == "memory"
    assert events[0]["data"]["timestamp"], "事件需带 timestamp（前端记用时）"
    assert events[1]["event"] == "status" and events[1]["data"]["stage"] == "memory_done"
    assert events[1]["data"]["timestamp"], "事件需带 timestamp（前端记用时）"
    assert injected["args"] == ("u1", "原始问题")
    assert captured["message"].endswith("</memory_context>"), "agent 收到的必须是注入后的消息"


@pytest.mark.asyncio
async def test_execute_agent_stream_no_status_or_injection_when_not_first_round(
    monkeypatch: pytest.MonkeyPatch,
):
    """非首轮：不发 status、不注入，消息原样透传——前缀缓存 append-only
    语义不变。"""
    from src.api.routes import chat as chat_route

    captured = {}
    _fake_agent_factory(captured, monkeypatch)

    async def fake_not_first_round(session_id, *, exclude_run_id=None):
        return False

    monkeypatch.setattr(chat_route, "_should_inject_session_memory", fake_not_first_round)

    async def unexpected_inject(message: str, *, user_id: str, raw_query: str | None) -> str:
        raise AssertionError("非首轮不应触发记忆注入")

    monkeypatch.setattr(chat_route, "inject_session_memory", unexpected_inject)

    events = []
    gen = chat_route._execute_agent_stream(
        session_id="s1",
        agent_id="fast_agent",
        message="base message",
        user_id="u1",
        presenter=_FakePresenter(),
        recommendation_input="原始问题",
    )
    async for ev in gen:
        events.append(ev)

    assert all(ev.get("event") != "status" for ev in events)
    assert captured["message"] == "base message", "executor 必须原样透传消息"


@pytest.mark.asyncio
async def test_execute_agent_stream_skips_memory_injection_on_hitl_resume(
    monkeypatch: pytest.MonkeyPatch,
):
    """HITL 恢复轮跳过注入（恢复语义不重注入），即使判定为首轮。"""
    from src.api.routes import chat as chat_route

    captured = {}
    _fake_agent_factory(captured, monkeypatch)

    async def fake_first_round(session_id, *, exclude_run_id=None):
        return True

    monkeypatch.setattr(chat_route, "_should_inject_session_memory", fake_first_round)

    async def unexpected_inject(message: str, *, user_id: str, raw_query: str | None) -> str:
        raise AssertionError("HITL 恢复轮不应触发记忆注入")

    monkeypatch.setattr(chat_route, "inject_session_memory", unexpected_inject)

    events = []
    gen = chat_route._execute_agent_stream(
        session_id="s1",
        agent_id="fast_agent",
        message="base message",
        user_id="u1",
        presenter=_FakePresenter(),
        recommendation_input="原始问题",
        hitl_resume={"goal_started_at": "2026-09-03T00:00:00+00:00"},
    )
    async for ev in gen:
        events.append(ev)

    assert all(ev.get("event") != "status" for ev in events)
    assert captured["message"] == "base message"


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
    # executor 侧判定：排除本 run 已写入的用户消息 trace
    await session_has_prior_messages("s1", exclude_run_id="run-current")
    assert counts["called_with"][-1] == {
        "session_id": "s1",
        "run_id": {"$ne": "run-current"},
    }
    await session_has_prior_messages("s1", exclude_run_id=None)
    assert counts["called_with"][-1] == {"session_id": "s1"}  # None 时不排除


@pytest.mark.asyncio
async def test_inject_session_memory_baseline_head_snapshot_tail(
    monkeypatch: pytest.MonkeyPatch,
):
    """executor 侧首轮装配的字节顺序与原 POST 侧完全一致：索引基线置头、
    相关记忆快照置尾——持久化与发送字节不变，前缀缓存语义不变。"""
    from src.infra.chat.session_baseline import inject_session_memory

    monkeypatch.setattr(memory_context.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(memory_context.settings, "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED", True)
    seen = {}

    async def fake_recall(user_id: str, query: str) -> list[dict]:
        seen["query"] = query
        return [_memory()]

    monkeypatch.setattr(memory_context, "_recall_memories_raw", fake_recall)

    async def fake_baseline(user_id):
        return "<memory_index_context>\n- 记忆索引行\n</memory_index_context>"

    monkeypatch.setattr(
        "src.infra.agent.middleware.prompt_injection.build_session_memory_baseline",
        fake_baseline,
    )

    out = await inject_session_memory(
        "[User message sent at 09:00+08:00]\n\n帮我总结项目进度",
        user_id="u1",
        raw_query="帮我总结项目进度",
    )

    assert seen["query"] == "帮我总结项目进度"  # 检索用原始消息，不用带时间戳文本
    assert (
        out.index("<memory_index_context>")
        < out.index("[User message sent at")
        < out.index("<memory_context>")
    )
    assert out.endswith("</memory_context>")  # 快照在尾部——前缀缓存安全位置


@pytest.mark.asyncio
async def test_assemble_first_turn_message_skips_memory_recall(
    monkeypatch: pytest.MonkeyPatch,
):
    """POST 装配只做零成本本地格式化：即使开关全开也不触发召回与基线构建
    （昂贵部分移至 executor，提交延迟与召回解耦）。"""
    from src.api.routes import chat as chat_route

    monkeypatch.setattr(memory_context.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(memory_context.settings, "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED", True)

    async def unexpected_recall(user_id: str, query: str) -> list[dict]:
        raise AssertionError("POST 装配不应触发记忆召回")

    monkeypatch.setattr(memory_context, "_recall_memories_raw", unexpected_recall)

    async def unexpected_baseline(user_id):
        raise AssertionError("POST 装配不应触发基线构建")

    monkeypatch.setattr(
        "src.infra.agent.middleware.prompt_injection.build_session_memory_baseline",
        unexpected_baseline,
    )

    msg, _tc = await chat_route.assemble_first_turn_message(
        raw_message="你好",
        user_timezone="Asia/Shanghai",
        enabled_skills=None,
        active_goal=None,
        auto_mode=False,
        user_id="u1",
        include_timestamp=True,
        last_tc_signature=None,
    )

    assert msg.startswith("[User message sent at")
    assert "<memory_context>" not in msg
    assert "<memory_index_context>" not in msg


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
