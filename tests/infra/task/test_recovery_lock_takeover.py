from __future__ import annotations

"""恢复锁僵死自愈：持锁实例死亡未释放时，不得把恢复堵满整个锁 TTL。

生产事故（staging 强杀演练）：垂死实例拿到恢复锁并提交 resume，随后实例死亡、
payload 被关闭清理删除，重投的 arq job 空转退出——锁无主人挂满 300s，期间
所有副本的扫描器都收到「已在其他实例中启动」。执行者心跳已死 + 锁龄超阈值
时必须原子接管（Lua 校验锁龄后覆写 token，旧持有者按 token 释放为 no-op）。
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from src.infra.task import recovery as recovery_module
from src.infra.task.recovery import TaskRecoveryService


class _LockHeldRedis:
    """模拟已被占用的恢复锁；eval 返回值可注入。"""

    def __init__(self, *, eval_result: int = 1) -> None:
        self.set_calls: list[tuple] = []
        self.eval_calls: list[tuple] = []
        self.eval_result = eval_result

    async def set(self, key, value, ex=None, nx=False):
        self.set_calls.append((key, value, ex, nx))
        return False  # 锁始终被占

    async def eval(self, script, num_keys, *args):
        self.eval_calls.append((script, num_keys, args))
        return self.eval_result


class _FreeLockRedis(_LockHeldRedis):
    async def set(self, key, value, ex=None, nx=False):
        self.set_calls.append((key, value, ex, nx))
        return True


class _FakeStorage:
    def __init__(self, session=None) -> None:
        self.session = session
        self.updates: list[tuple[str, Any]] = []

    async def update(self, session_id, session_update) -> None:
        self.updates.append((session_id, session_update))


def _make_service(
    monkeypatch: pytest.MonkeyPatch,
    redis: Any,
    *,
    stale: bool,
) -> tuple[TaskRecoveryService, AsyncMock]:
    session = SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="search",
        metadata={
            "current_run_id": "run-old",
            "task_status": "failed",
            "task_recoverable": True,
            "task_error_code": "server_restart",
            "agent_id": "search",
            "executor_key": "agent_stream",
            "resume_attempts": 0,
        },
    )
    submit_task = AsyncMock(return_value=("run-old", "trace-1"))

    async def _stale_flag(run_id: str) -> bool:
        return stale

    service = TaskRecoveryService(
        storage=_FakeStorage(session),
        run_info={},
        heartbeat=SimpleNamespace(check_exists=lambda run_id: False, is_stale=_stale_flag),
        ensure_executor=lambda: SimpleNamespace(),
        submit_task=submit_task,
        mark_run_failed=AsyncMock(),
    )

    class _FakeUserStorage:
        async def get_by_id(self, user_id):
            return SimpleNamespace(metadata={"language": "zh-CN"}, roles=[])

    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: redis)
    monkeypatch.setattr(recovery_module, "UserStorage", _FakeUserStorage)
    monkeypatch.setattr(recovery_module, "get_trace_storage", _FakeTraceStorage)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: SimpleNamespace(redis=SimpleNamespace(xrange=AsyncMock(return_value=[]))),
    )
    monkeypatch.setattr(recovery_module, "get_registered_executor", lambda key: _noop_executor)
    monkeypatch.setattr(recovery_module, "get_concurrency_limiter", lambda: _FakeLimiter())
    monkeypatch.setattr(recovery_module, "_resolve_recovery_agent_id", lambda m, s: "search")
    monkeypatch.setattr("src.kernel.config.settings.TASK_BACKEND", "local")
    return service, submit_task


class _FakeTraceStorage:
    reopened: list[str] = []

    def __init__(self) -> None:
        self.collection = SimpleNamespace(
            find=lambda query, projection=None: SimpleNamespace(
                sort=lambda k, d=None: SimpleNamespace(
                    limit=lambda n: SimpleNamespace(to_list=_return_trace_docs)
                )
            )
        )

    async def reopen_interrupted_trace(self, trace_id: str) -> bool:
        self.reopened.append(trace_id)
        return True


async def _return_trace_docs(length=None):
    return [{"trace_id": "trace-1"}]


class _FakeLimiter:
    async def try_acquire_run_slot(self, user_id, run_id) -> bool:
        return True

    async def release(self, user_id, run_id, dequeue=True) -> None:
        return None


async def _noop_executor(*args, **kwargs):
    if False:
        yield None


_FakeTraceStorageInstance = _FakeTraceStorage()


@pytest.mark.asyncio
async def test_takes_over_stale_aged_lock_when_executor_dead(monkeypatch) -> None:
    redis = _LockHeldRedis(eval_result=1)
    service, submit_task = _make_service(monkeypatch, redis, stale=True)

    result = await service.resume_interrupted_run(_session_of(service), "run-old", "server_restart")

    assert result["success"] is True
    assert redis.eval_calls, "锁被占时应尝试 Lua 僵死接管"
    submit_task.assert_awaited_once()


@pytest.mark.asyncio
async def test_respects_fresh_lock_held_by_live_recovery(monkeypatch) -> None:
    redis = _LockHeldRedis(eval_result=0)
    service, submit_task = _make_service(monkeypatch, redis, stale=True)

    result = await service.resume_interrupted_run(_session_of(service), "run-old", "server_restart")

    assert result["success"] is False
    assert "已在其他实例中启动" in result["message"]
    submit_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_no_takeover_attempt_when_executor_heartbeat_fresh(monkeypatch) -> None:
    redis = _LockHeldRedis(eval_result=1)
    service, submit_task = _make_service(monkeypatch, redis, stale=False)

    result = await service.resume_interrupted_run(_session_of(service), "run-old", "server_restart")

    assert result["success"] is False
    assert "已在其他实例中启动" in result["message"]
    assert redis.eval_calls == [], "心跳新鲜时不得动锁（可能是活实例在恢复）"
    submit_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_normal_acquire_skips_takeover_path(monkeypatch) -> None:
    redis = _FreeLockRedis()
    service, submit_task = _make_service(monkeypatch, redis, stale=True)

    result = await service.resume_interrupted_run(_session_of(service), "run-old", "server_restart")

    assert result["success"] is True
    assert redis.eval_calls == [], "NX 直接拿到锁时不应触发接管脚本"
    submit_task.assert_awaited_once()


def _session_of(service: TaskRecoveryService) -> Any:
    return service._storage.session
