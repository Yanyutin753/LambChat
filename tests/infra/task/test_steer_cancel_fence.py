"""Cancellation must win over a delayed POST on another API replica."""

import asyncio

from src.infra.task.steer import SteerItem, SteerQueue
from tests.infra.test_chat_lease_ownership import lease_redis as lease_redis


async def test_cancel_before_post_suppresses_late_enqueue():
    queue = SteerQueue(redis=None)
    assert not await queue.remove_by_id("session", "withdrawn")
    assert await queue.enqueue_item("session", SteerItem("withdrawn", "late")) == -1
    assert await queue.list_items("session") == []


async def test_cancelled_id_cannot_be_retried_after_new_run_cleanup():
    queue = SteerQueue(redis=None)
    await queue.enqueue_item("session", SteerItem("withdrawn", "late"))
    assert await queue.remove_by_id("session", "withdrawn")
    await queue.clear_session("session")
    assert await queue.enqueue_item("session", SteerItem("withdrawn", "late")) == -1
    assert await queue.list_items("session") == []


async def test_cancel_identity_does_not_remove_other_sessions_or_same_text():
    queue = SteerQueue(redis=None)
    await queue.remove_by_id("first", "withdrawn")
    await queue.enqueue_item("first", SteerItem("keep", "same"))
    await queue.enqueue_item("second", SteerItem("withdrawn", "same"))
    assert [item.id for item in await queue.list_items("first")] == ["keep"]
    assert [item.id for item in await queue.list_items("second")] == ["withdrawn"]


async def test_promotion_cleanup_preserves_the_identity_for_an_explicit_retry():
    queue = SteerQueue(redis=None)
    await queue.enqueue_item("session", SteerItem("retry", "not withdrawn"))
    assert await queue.remove_by_id("session", "retry", prevent_reenqueue=False)
    assert await queue.enqueue_item("session", SteerItem("retry", "not withdrawn")) == 1


async def test_promotion_cleanup_cannot_erase_an_existing_withdrawal(lease_redis):
    queue = SteerQueue(redis=lease_redis)
    await queue.remove_by_id("session", "withdrawn")
    await queue.remove_by_id("session", "withdrawn", prevent_reenqueue=False)
    assert await queue.enqueue_item("session", SteerItem("withdrawn", "late")) == -1


async def test_cross_replica_delete_before_post_suppresses_late_enqueue(lease_redis):
    first, second = SteerQueue(redis=lease_redis), SteerQueue(redis=lease_redis)
    assert not await second.remove_by_id("session", "withdrawn")
    result = await first.enqueue_item(
        "session", SteerItem("withdrawn", "", attachments=[{"key": "private-file"}])
    )
    assert result == -1
    assert await first.list_items("session") == []
    assert await second.drain_items("session") == []


async def test_concurrent_cross_replica_post_and_cancel_leave_no_pending_item(lease_redis):
    first, second = SteerQueue(redis=lease_redis), SteerQueue(redis=lease_redis)
    await asyncio.gather(
        second.remove_by_id("session", "withdrawn"),
        first.enqueue_item("session", SteerItem("withdrawn", "late")),
    )
    assert await first.list_items("session") == []
    assert await second.enqueue_item("session", SteerItem("withdrawn", "late")) == -1


async def test_cancel_fence_survives_queue_cleanup_and_expires(lease_redis):
    first, second = SteerQueue(redis=lease_redis), SteerQueue(redis=lease_redis)
    await first.remove_by_id("session", "withdrawn")
    await second.clear_session("session")
    keys = await lease_redis.keys("lambchat:steer:session*")
    assert len(keys) == 1
    assert 0 < await lease_redis.ttl(keys[0]) <= 86400
    assert await second.enqueue_item("session", SteerItem("withdrawn", "late")) == -1
    await lease_redis.expire(keys[0], -1)
    assert await second.enqueue_item("session", SteerItem("withdrawn", "new attempt")) == 1


async def test_cancel_does_not_retract_an_already_claimed_item(lease_redis):
    first, second = SteerQueue(redis=lease_redis), SteerQueue(redis=lease_redis)
    await first.enqueue_item("session", SteerItem("claimed", "delivering"))
    assert [item.id for item in await first.drain_items("session")] == ["claimed"]
    assert not await second.remove_by_id("session", "claimed")
    assert [item.id for item in await second.list_items("session")] == ["claimed"]
    await first.ack_items("session")
    assert await second.enqueue_item("session", SteerItem("claimed", "late retry")) == -2
    assert await second.list_items("session") == []


async def test_expired_claim_preserves_payload_for_another_replica(lease_redis):
    first, second = SteerQueue(redis=lease_redis), SteerQueue(redis=lease_redis)
    item = SteerItem("claimed", "", attachments=[{"key": "private-file"}])
    await first.enqueue_item("session", item)
    claimed = await first.drain_items("session")
    assert claimed == [item]
    assert 86395 <= await lease_redis.ttl(first._inflight_key("session")) <= 86400
    assert 3595 <= await lease_redis.ttl(first._lease_key("session")) <= 3600
    assert await second.drain_items("session") == []

    # Simulate an abandoned lease expiring while its durable payload remains.
    await lease_redis.expire(first._lease_key("session"), -1)
    await lease_redis.expire(first._inflight_key("session"), 120)
    assert await second.drain_items("session") == [item]
    assert 86395 <= await lease_redis.ttl(first._inflight_key("session")) <= 86400
    replacement_owner = await lease_redis.get(first._lease_key("session"))

    assert await first.ack_items("session") is False
    await first.requeue_front_items("session", claimed)
    assert await lease_redis.get(first._lease_key("session")) == replacement_owner
    assert await lease_redis.lrange(first._key("session"), 0, -1) == []
    assert await second.list_items("session") == [item]
    assert await second.list_receipts("session") == []

    assert await second.ack_items("session") is True
    assert await second.list_items("session") == []
    assert await second.list_receipts("session") == [item]


async def test_settled_query_is_read_only_and_receipt_wins_across_replicas(lease_redis):
    first, second = SteerQueue(redis=lease_redis), SteerQueue(redis=lease_redis)
    await first.enqueue_item("session", SteerItem("delivered", "once"))
    await first.drain_items("session")
    assert await first.ack_items("session")
    await first.remove_by_id("session", "delivered")
    await first.remove_by_id("session", "cancelled")
    before = {key: await lease_redis.dump(key) for key in await lease_redis.keys("lambchat:steer:*")}
    assert await second.settled_outcome("session", "delivered") == "delivered"
    assert await second.settled_outcome("session", "cancelled") == "cancelled"
    assert await second.settled_outcome("session", "new") is None
    assert await second.settled_outcome("other", "delivered") is None
    after = {key: await lease_redis.dump(key) for key in await lease_redis.keys("lambchat:steer:*")}
    assert after == before


async def test_settled_query_ignores_expired_receipts_without_deleting_them(lease_redis, monkeypatch):
    import src.infra.task.steer as module

    now = 1000.0
    monkeypatch.setattr(module.time, "time", lambda: now)
    queue = SteerQueue(redis=lease_redis)
    await queue.enqueue_item("session", SteerItem("expired", "old"))
    await queue.drain_items("session")
    assert await queue.ack_items("session")
    before = await lease_redis.lrange(queue._receipts_key("session"), 0, -1)
    now += 86401
    assert await queue.settled_outcome("session", "expired") is None
    assert await lease_redis.lrange(queue._receipts_key("session"), 0, -1) == before
