"""SteerQueue（运行中插话消息队列）单元测试。"""

from src.infra.task.steer import get_steer_queue


async def test_enqueue_then_drain_returns_fifo_and_empties() -> None:
    queue = get_steer_queue()

    await queue.enqueue("session-1", "第一条")
    await queue.enqueue("session-1", "第二条")

    assert await queue.drain("session-1") == ["第一条", "第二条"]
    assert await queue.drain("session-1") == []


async def test_queues_are_isolated_per_session() -> None:
    queue = get_steer_queue()

    await queue.enqueue("session-a", "给 A")
    await queue.enqueue("session-b", "给 B")

    assert await queue.drain("session-a") == ["给 A"]
    assert await queue.drain("session-b") == ["给 B"]


async def test_drain_unknown_session_returns_empty() -> None:
    assert await get_steer_queue().drain("nope") == []


async def test_enqueue_returns_pending_count() -> None:
    queue = get_steer_queue()

    assert await queue.enqueue("session-c", "one") == 1
    assert await queue.enqueue("session-c", "two") == 2
