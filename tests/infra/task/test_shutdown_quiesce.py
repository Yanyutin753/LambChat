from __future__ import annotations

"""关闭静默：实例进入 lifespan 关闭后不得再发起新的恢复/接管。

生产事故（staging 强杀演练）：旧 Pod 收到终止信号后，executor 先因依赖关闭
而失败并标记 recoverable，而 15s 周期孤儿扫描器仍存活——垂死实例把恢复任务
提交给自己即将关闭的 arq worker，run:resumed 后随即被再次杀掉。结果：
多一次无效生成、payload 被关闭清理删除、恢复锁被死实例占满整个 TTL。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.task import startup_cleanup as startup_cleanup_module
from src.infra.task.lifecycle import clear_shutting_down, is_shutting_down, mark_shutting_down


@pytest.fixture(autouse=True)
def _reset_shutdown_flag():
    clear_shutting_down()
    yield
    clear_shutting_down()


def test_lifecycle_flag_roundtrip() -> None:
    assert is_shutting_down() is False
    mark_shutting_down()
    assert is_shutting_down() is True
    clear_shutting_down()
    assert is_shutting_down() is False


@pytest.mark.asyncio
async def test_cleanup_stale_tasks_noops_when_shutting_down(monkeypatch) -> None:
    service = startup_cleanup_module.TaskStartupCleanupService(
        storage=SimpleNamespace(
            collection=SimpleNamespace(find=_fail("find")),
        ),
        heartbeat=SimpleNamespace(check_exists=_fail("check_exists")),
        ensure_executor=_fail("ensure_executor"),
        load_session_record=_fail("load_session_record"),
        resume_interrupted_run=_fail("resume_interrupted_run"),
    )

    mark_shutting_down()

    # 不得触碰存储/心跳/恢复路径
    await service.cleanup_stale_tasks()
    await service.cleanup_stale_tasks(running_only=True)


def _fail(name: str):
    def _raise(*args, **kwargs):
        raise AssertionError(f"shutdown 中不应调用 {name}")

    return _raise


@pytest.mark.asyncio
async def test_orphan_recovery_skips_when_shutting_down(monkeypatch) -> None:
    from src.infra.task import orphan_recovery

    task_manager = SimpleNamespace(cleanup_stale_tasks=AsyncMock())
    monkeypatch.setattr(orphan_recovery, "get_task_manager", lambda: task_manager)

    mark_shutting_down()

    result = await orphan_recovery.run_scheduled_orphan_recovery()

    assert result["status"] == "skipped"
    task_manager.cleanup_stale_tasks.assert_not_awaited()


@pytest.mark.asyncio
async def test_orphan_recovery_runs_when_not_shutting_down(monkeypatch) -> None:
    from src.infra.task import orphan_recovery

    task_manager = SimpleNamespace(cleanup_stale_tasks=AsyncMock())
    monkeypatch.setattr(orphan_recovery, "get_task_manager", lambda: task_manager)

    result = await orphan_recovery.run_scheduled_orphan_recovery()

    assert result["status"] == "ok"
    task_manager.cleanup_stale_tasks.assert_awaited_once_with(running_only=True)


@pytest.mark.asyncio
async def test_worker_restart_recovery_skips_when_shutting_down(monkeypatch) -> None:
    from src.infra.task import arq_runtime

    task_manager = SimpleNamespace(cleanup_stale_tasks=AsyncMock())
    # 函数体内延迟 `from .manager import get_task_manager`，patch 模块属性即可
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: task_manager)

    mark_shutting_down()

    await arq_runtime._recover_stale_tasks_after_worker_restart()

    task_manager.cleanup_stale_tasks.assert_not_awaited()
