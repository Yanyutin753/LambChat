"""SteerMiddleware + SteerQueue 真 Redis 集成测试。

复现生产部署形态（Redis 队列多 worker 共享）：验证「drain 即送达」在
Redis 路径上的完整不变量——注入后队列视角必须干净（pending/inflight
清空），否则 run 终态的 ``emit_undelivered_steer_events`` 会把已送达的
插话误报为 ``steer:undelivered``，前端补发流程会把同一条消息再发一次
（用户看到重复消息）。

本机/CI 无 Redis 时自动跳过（非静默：标记 skip 留痕）。
"""

from uuid import uuid4

import pytest

from src.infra.agent.middleware.steer import SteerMiddleware
from src.infra.task.steer import SteerItem, SteerQueue, emit_undelivered_steer_events


def _redis_available() -> bool:
    import asyncio

    async def _probe() -> bool:
        try:
            from src.infra.storage.redis import create_redis_client

            client = create_redis_client()
            try:
                return bool(await client.ping())
            finally:
                await client.aclose()
        except Exception:
            return False

    try:
        return asyncio.run(_probe())
    except RuntimeError:
        return False


redis_required = pytest.mark.skipif(not _redis_available(), reason="local Redis unreachable")


class _RecordingPresenter:
    run_id = "run-redis-integration"

    def __init__(self) -> None:
        self.saved: list[dict] = []

    async def save_event(self, event: dict) -> None:
        self.saved.append(event)


@pytest.fixture
async def redis_queue(monkeypatch):
    """真 Redis 队列 + 会话级隔离 + 用后清理。

    conftest 的 autouse fixture 会把队列单例换成进程内实现；这里重新把
    ``get_steer_queue`` 单例绑回真 Redis 队列，中间件 drain/ack 才走
    Redis 路径（生产部署形态），结束后还原。
    """
    import src.infra.task.steer as steer_module

    queue = SteerQueue()
    session_id = f"steer-redis-test-{uuid4().hex[:8]}"
    previous = steer_module._steer_queue
    steer_module._steer_queue = queue
    try:
        yield queue, session_id
    finally:
        steer_module._steer_queue = previous
        await queue.clear_session(session_id)


@redis_required
async def test_injected_steer_is_not_reported_undelivered_at_run_end(redis_queue) -> None:
    """注入成功的插话在 run 终态不得被误报 steer:undelivered（前端会补发导致重复）。"""
    queue, session_id = redis_queue
    await queue.enqueue_item(session_id, SteerItem(id="steer-delivered", content="已送达的插话"))

    middleware = SteerMiddleware(session_id=session_id, presenter=_RecordingPresenter())
    update = await middleware.abefore_model({"messages": []}, None)
    assert update is not None  # 注入成功

    # executor 终态路径：列出残留插话并写 steer:undelivered
    presenter = _RecordingPresenter()
    written = await emit_undelivered_steer_events(
        session_id, run_id="run-end", presenter=presenter, queue=queue
    )

    assert written == 0, f"已送达插话被误报 undelivered：{presenter.saved}"
    assert presenter.saved == []
    # 队列视角必须干净（list_items 读 pending+inflight，被 enqueue 幂等与补发流程依赖）
    assert await queue.list_items(session_id) == []


@redis_required
async def test_injected_steer_survives_across_queue_instances(redis_queue) -> None:
    """多 worker 形态：drain 后另起队列实例，inflight/lease 不得残留。"""
    queue, session_id = redis_queue
    await queue.enqueue_item(session_id, SteerItem(id="steer-cross", content="跨实例插话"))

    middleware = SteerMiddleware(session_id=session_id)
    assert await middleware.abefore_model({"messages": []}, None) is not None

    # 模拟另一个 worker / 进程重启后的队列实例
    other = SteerQueue()
    try:
        assert await other.list_items(session_id) == []
    finally:
        await other.clear_session(session_id)


@redis_required
async def test_never_injected_steer_is_still_reported_undelivered(redis_queue) -> None:
    """对照：未被注入的插话仍照常落 steer:undelivered（不丢消息语义不变）。"""
    queue, session_id = redis_queue
    await queue.enqueue_item(session_id, SteerItem(id="steer-pending", content="未注入的插话"))

    presenter = _RecordingPresenter()
    written = await emit_undelivered_steer_events(
        session_id, run_id="run-pending", presenter=presenter, queue=queue
    )

    assert written == 1
    assert presenter.saved[0]["event"] == "steer:undelivered"
    assert presenter.saved[0]["data"]["message_id"] == "steer-pending"
