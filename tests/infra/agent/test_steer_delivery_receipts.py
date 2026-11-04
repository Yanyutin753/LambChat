"""Delivery receipts close the ACK-to-checkpoint loss window."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.errors import NodeCancelledError

from src.infra.agent.middleware.steer import SteerMiddleware
from src.infra.task.steer import SteerItem, SteerQueue
from tests.infra.test_chat_lease_ownership import lease_redis as lease_redis


class Model(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


async def test_consumed_id_cannot_reenqueue_on_another_replica(lease_redis):
    first, second = SteerQueue(redis=lease_redis), SteerQueue(redis=lease_redis)
    await first.enqueue_item("session", SteerItem("delivered", "once"))
    await first.drain_items("session")
    await first.ack_items("session")
    assert await second.enqueue_item("session", SteerItem("delivered", "once")) == -2
    assert await second.list_items("session") == []
    # An already delivered receipt wins over a later withdrawal marker.
    await second.remove_by_id("session", "delivered")
    assert await second.enqueue_item("session", SteerItem("delivered", "once")) == -2
    assert await second.enqueue_item("other-session", SteerItem("delivered", "other")) == 1


async def test_memory_receipts_deduplicate_and_survive_run_cleanup():
    queue = SteerQueue(redis=None)
    await queue.enqueue_item("session", SteerItem("delivered", "once"))
    await queue.drain_items("session")
    await queue.ack_items("session")
    await queue.clear_session("session")
    assert await queue.enqueue_item("session", SteerItem("delivered", "once")) == -2
    assert [item.id for item in await queue.list_receipts("session")] == ["delivered"]


async def test_recovered_receipt_preserves_attachment_payload(monkeypatch):
    import src.infra.task.steer as module

    queue = SteerQueue(redis=None)
    attachment = {"key": "private/object", "name": "report.txt", "url": "/api/private/file"}
    await queue.enqueue_item("session", SteerItem("attachment", "", attachments=[attachment]))
    await queue.drain_items("session")
    await queue.ack_items("session")
    receipt_ack = AsyncMock(side_effect=AssertionError("receipt recovery must not ACK"))
    monkeypatch.setattr(queue, "ack_items", receipt_ack)
    monkeypatch.setattr(module, "_steer_queue", queue)
    presenter = AsyncMock()
    update = await SteerMiddleware(session_id="session", presenter=presenter).abefore_model(
        {"messages": []}, None
    )
    assert update and update["messages"][0].id == "steer:attachment"
    assert presenter.save_event.call_args.args[0]["data"]["attachments"] == [attachment]
    receipt_ack.assert_not_awaited()


async def test_replaced_claim_cannot_commit_middleware_state(lease_redis, monkeypatch):
    import src.infra.task.steer as module

    first, second = SteerQueue(redis=lease_redis), SteerQueue(redis=lease_redis)
    item = SteerItem("claimed", "must belong to replacement")
    await first.enqueue_item("session", item)
    drain = first.drain_items

    async def drain_then_lose_lease(sid):
        items = await drain(sid)
        await lease_redis.expire(first._lease_key(sid), -1)
        assert await second.drain_items(sid) == [item]
        return items

    monkeypatch.setattr(first, "drain_items", drain_then_lose_lease)
    monkeypatch.setattr(module, "_steer_queue", first)
    presenter = AsyncMock()
    with pytest.raises(RuntimeError, match="Steer delivery lease lost"):
        await SteerMiddleware(session_id="session", presenter=presenter).abefore_model(
            {"messages": []}, None
        )
    presenter.save_event.assert_not_awaited()
    assert await second.list_items("session") == [item]
    assert await second.list_receipts("session") == []
    assert await second.ack_items("session") is True


@pytest.mark.parametrize("committed", [False, True])
async def test_uncertain_ack_does_not_commit_state_and_retry_recovers(monkeypatch, committed):
    import src.infra.task.steer as module

    queue = SteerQueue(redis=None)
    monkeypatch.setattr(module, "_steer_queue", queue)
    await queue.enqueue_item("session", SteerItem("uncertain", "retained"))
    ack = queue.ack_items

    async def uncertain_ack(sid):
        if committed:
            assert await ack(sid) is True
        raise ConnectionError("ACK response unavailable")

    monkeypatch.setattr(queue, "ack_items", uncertain_ack)
    presenter = AsyncMock()
    middleware = SteerMiddleware(session_id="session", presenter=presenter)
    with pytest.raises(ConnectionError, match="ACK response unavailable"):
        await middleware.abefore_model({"messages": []}, None)
    presenter.save_event.assert_not_awaited()
    monkeypatch.setattr(queue, "ack_items", ack)
    update = await middleware.abefore_model({"messages": []}, None)
    assert update and [message.id for message in update["messages"]] == ["steer:uncertain"]
    assert await middleware.abefore_model(update, None) is None


async def test_receipts_expire_without_extending_older_entries(lease_redis, monkeypatch):
    import src.infra.task.steer as module

    now = 1000.0
    monkeypatch.setattr(module.time, "time", lambda: now)
    queue = SteerQueue(redis=lease_redis)
    await queue.enqueue_item("session", SteerItem("first", "old"))
    await queue.drain_items("session")
    await queue.ack_items("session")
    now += 86401
    await queue.enqueue_item("session", SteerItem("second", "new"))
    await queue.drain_items("session")
    await queue.ack_items("session")
    assert [item.id for item in await queue.list_receipts("session")] == ["second"]


async def test_worker_interruption_after_ack_recovers_once_from_checkpoint(
    lease_redis, monkeypatch
):
    import src.infra.task.steer as module

    queue = SteerQueue(redis=lease_redis)
    monkeypatch.setattr(module, "_steer_queue", queue)
    await queue.enqueue_item("session", SteerItem("survive", "retained after interruption"))
    ack = queue.ack_items

    async def ack_then_interrupt(sid):
        await ack(sid)
        raise asyncio.CancelledError("after ACK before checkpoint")

    monkeypatch.setattr(queue, "ack_items", ack_then_interrupt)
    saver = MemorySaver()
    config = {"configurable": {"thread_id": "session"}}

    def graph():
        return create_agent(
            Model(responses=[AIMessage(content="done")]),
            tools=[],
            middleware=[SteerMiddleware(session_id="session", presenter=AsyncMock())],
            checkpointer=saver,
        )

    with pytest.raises(NodeCancelledError) as caught:
        await graph().ainvoke({"messages": [HumanMessage(content="initial")]}, config)
    assert isinstance(caught.value.__cause__, asyncio.CancelledError)
    monkeypatch.setattr(module, "_steer_queue", SteerQueue(redis=lease_redis))
    recovered_graph = graph()
    result = await recovered_graph.ainvoke(None, config)
    assert (
        sum(message.content == "retained after interruption" for message in result["messages"]) == 1
    )
    again = await recovered_graph.ainvoke({"messages": [HumanMessage(content="next turn")]}, config)
    assert (
        sum(message.content == "retained after interruption" for message in again["messages"]) == 1
    )


async def test_applied_receipt_survives_message_compaction_and_old_checkpoint(monkeypatch):
    import src.infra.task.steer as module

    queue = SteerQueue(redis=None)
    monkeypatch.setattr(module, "_steer_queue", queue)
    await queue.enqueue_item("session", SteerItem("compact", "original detail"))
    middleware = SteerMiddleware(session_id="session", presenter=AsyncMock())
    # An old checkpoint has no receipt field and remains supported.
    update = await middleware.abefore_model({"messages": []}, None)
    assert update and len(update["messages"]) == 1
    compacted = {**update, "messages": [HumanMessage(content="summary of earlier details")]}
    assert await middleware.abefore_model(compacted, None) is None
