"""聊天模型侧消息不得注入跨会话记忆。"""

from __future__ import annotations

import pytest

from src.infra.chat.model_facing import build_model_facing_message


def _fake_agent_factory(captured: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAgent:
        def stream(self, message, *args, **kwargs):
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
async def test_model_facing_message_never_contains_memory_blocks():
    message = await build_model_facing_message(
        raw_message="曼玲粥的皮蛋供应商是谁？",
        user_timezone="Asia/Shanghai",
        enabled_skills=None,
        active_goal=None,
        auto_mode=False,
        user_id="u1",
        include_memory=True,
    )

    assert message.startswith("[User message sent at:")
    assert message.rstrip().endswith("曼玲粥的皮蛋供应商是谁？")
    assert "<memory_context>" not in message
    assert "<memory_index_context>" not in message
    assert "<memory_index>" not in message


@pytest.mark.asyncio
async def test_execute_agent_stream_never_injects_memory_into_user_message(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.api.routes import chat as chat_route

    captured = {}
    _fake_agent_factory(captured, monkeypatch)

    events = []
    gen = chat_route._execute_agent_stream(
        session_id="s1",
        agent_id="fast_agent",
        message="base message",
        user_id="u1",
        presenter=_FakePresenter(),
        recommendation_input="原始问题",
    )
    async for event in gen:
        events.append(event)

    assert all(
        not (
            event.get("event") == "status"
            and event.get("data", {}).get("stage") in {"memory", "memory_done"}
        )
        for event in events
    )
    assert captured["message"] == "base message"


@pytest.mark.asyncio
async def test_assemble_first_turn_message_does_not_touch_memory(monkeypatch):
    from src.api.routes import chat as chat_route

    async def unexpected_backend():
        raise AssertionError("message assembly must not initialize memory")

    monkeypatch.setattr("src.infra.memory.tools._get_backend", unexpected_backend)

    message, _ = await chat_route.assemble_first_turn_message(
        raw_message="你好",
        user_timezone="Asia/Shanghai",
        enabled_skills=None,
        active_goal=None,
        auto_mode=False,
        user_id="u1",
        include_timestamp=True,
        last_tc_signature=None,
    )

    assert message.startswith("[User message sent at:")
    assert "<memory" not in message


def test_chat_route_has_no_memory_message_injection_symbols():
    from inspect import getsource

    from src.api.routes import chat as chat_route

    source = getsource(chat_route)
    assert "inject_session_memory" not in source
    assert "_should_inject_session_memory" not in source
    assert '"stage": "memory"' not in source
