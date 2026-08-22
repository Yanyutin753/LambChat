"""SteerQueue（运行中插话消息队列）单元测试。"""

from src.infra.task.steer import SteerItem, SteerQueue


async def test_default_queue_does_not_silently_fallback_when_redis_is_unavailable(
    monkeypatch,
) -> None:
    async def fail_ping(*_args, **_kwargs):
        raise ConnectionError("redis unavailable")

    class BrokenRedis:
        async def ping(self):
            return await fail_ping()

    monkeypatch.setattr(
        "src.infra.storage.redis.create_redis_client",
        lambda **_kwargs: BrokenRedis(),
    )
    queue = SteerQueue()
    try:
        await queue.enqueue("distributed-only", "must fail closed")
    except RuntimeError as exc:
        assert "requires Redis" in str(exc)
    else:
        raise AssertionError("queue must not use a process-local fallback")


async def test_enqueue_then_drain_returns_fifo_and_empties() -> None:
    queue = SteerQueue(redis=None)

    await queue.enqueue("session-1", "第一条")
    await queue.enqueue("session-1", "第二条")

    assert await queue.drain("session-1") == ["第一条", "第二条"]
    assert await queue.drain("session-1") == []


async def test_queues_are_isolated_per_session() -> None:
    queue = SteerQueue(redis=None)

    await queue.enqueue("session-a", "给 A")
    await queue.enqueue("session-b", "给 B")

    assert await queue.drain("session-a") == ["给 A"]
    assert await queue.drain("session-b") == ["给 B"]


async def test_drain_unknown_session_returns_empty() -> None:
    assert await SteerQueue(redis=None).drain("nope") == []


async def test_enqueue_returns_pending_count() -> None:
    queue = SteerQueue(redis=None)

    assert await queue.enqueue("session-c", "one") == 1
    assert await queue.enqueue("session-c", "two") == 2


async def test_remove_cancels_first_matching_message() -> None:
    queue = SteerQueue(redis=None)

    await queue.enqueue("session-r", "keep")
    await queue.enqueue("session-r", "drop")
    await queue.enqueue("session-r", "drop")

    assert await queue.remove("session-r", "drop") is True
    assert await queue.drain("session-r") == ["keep", "drop"]

    # 不存在的内容返回 False
    assert await queue.remove("session-r", "missing") is False


async def test_enqueue_is_idempotent_by_message_id_and_cancel_does_not_confuse_duplicate_text() -> (
    None
):
    queue = SteerQueue(redis=None)
    first = SteerItem(id="msg-1", content="相同内容")
    second = SteerItem(id="msg-2", content="相同内容")

    assert await queue.enqueue_item("session-id", first) == 1
    assert await queue.enqueue_item("session-id", first) == 1
    assert await queue.enqueue_item("session-id", second) == 2

    assert await queue.remove_by_id("session-id", "msg-2") is True
    drained = await queue.drain_items("session-id")
    assert [item.id for item in drained] == ["msg-1"]
    assert drained[0].content == "相同内容"


async def test_queue_preserves_attachments_with_steer_item() -> None:
    queue = SteerQueue(redis=None)
    attachments = [
        {
            "id": "file-1",
            "key": "uploads/file-1",
            "name": "截图.png",
            "type": "image",
            "mime_type": "image/png",
            "size": 42,
            "url": "/api/files/file-1",
        }
    ]

    await queue.enqueue_item(
        "session-attachments",
        SteerItem(id="steer-attachment", content="看看这张图", attachments=attachments),
    )

    drained = await queue.drain_items("session-attachments")
    assert drained[0].attachments == attachments


async def test_clear_session_empties_pending_queue() -> None:
    """run 结束后残留的插话不应被注入下一个无关的 run。"""
    queue = SteerQueue(redis=None)
    await queue.enqueue("session-clear", "残留插话一")
    await queue.enqueue("session-clear", "残留插话二")

    await queue.clear_session("session-clear")

    assert await queue.list_items("session-clear") == []
    assert await queue.drain_items("session-clear") == []


async def test_clear_session_is_idempotent_for_unknown_session() -> None:
    queue = SteerQueue(redis=None)
    await queue.clear_session("never-existed")

    assert await queue.drain_items("never-existed") == []


async def test_clear_session_redis_deletes_pending_inflight_and_lease_keys() -> None:
    """Redis 路径必须同时清 pending/inflight/lease 三个键（多 worker 共享状态）。"""
    deleted: list[str] = []

    class _FakeRedis:
        async def ping(self):
            return True

        async def delete(self, *keys):
            deleted.extend(keys)
            return len(keys)

    queue = SteerQueue(redis=_FakeRedis())  # type: ignore[arg-type]

    await queue.clear_session("session-redis")

    assert sorted(deleted) == sorted(
        [
            "lambchat:steer:session-redis",
            "lambchat:steer:session-redis:inflight",
            "lambchat:steer:session-redis:lease",
        ]
    )
