"""取消路径注册表的有界性(issue #1139)。

双 API 副本 + arq worker 拓扑下,cancel() 在「不执行该 run」的副本上也会写
入 ``_run_info`` / ``_interrupted_runs``,而本地完成回调永远不会清理这些
条目——写路径必须自带节流修剪,注册表才能回到有界。
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.infra.task.cancellation as cancellation_module
import src.infra.task.manager as manager_module
from src.infra.task.cancellation import TaskCancellation
from src.infra.task.manager import BackgroundTaskManager


@pytest.fixture(autouse=True)
def _reset_registries():
    cancellation_module._interrupted_runs.clear()
    manager_module._last_cancel_probe_prune = 0.0
    cancellation_module._last_write_cleanup_ts = 0.0
    yield
    cancellation_module._interrupted_runs.clear()


def test_set_local_interrupt_prunes_expired_entries():
    cancellation_module._interrupted_runs["expired-run"] = time.time() - (
        cancellation_module._INTERRUPT_MAX_AGE + 60
    )

    TaskCancellation.set_local_interrupt("fresh-run")

    assert "expired-run" not in cancellation_module._interrupted_runs
    assert "fresh-run" in cancellation_module._interrupted_runs


def test_write_path_cleanup_is_throttled():
    cancellation_module._last_write_cleanup_ts = time.monotonic()
    cancellation_module._interrupted_runs["expired-run"] = 0.0

    TaskCancellation.set_local_interrupt("fresh-run")

    assert "expired-run" in cancellation_module._interrupted_runs


def test_prune_only_touches_cancel_probe_entries():
    manager = BackgroundTaskManager()
    manager._run_info["real-run"] = {"session_id": "s1"}
    manager._run_info["stale-cancel"] = {
        "_cancel_probe": True,
        "_cancel_probe_ts": time.monotonic() - (manager_module._CANCEL_PROBE_MAX_AGE + 60),
        "session_id": "s2",
    }
    manager._run_info["recent-cancel"] = {
        "_cancel_probe": True,
        "_cancel_probe_ts": time.monotonic(),
        "session_id": "s3",
    }

    manager._prune_cancel_probe_run_info()

    assert "real-run" in manager._run_info
    assert "recent-cancel" in manager._run_info
    assert "stale-cancel" not in manager._run_info


async def test_build_run_info_marks_probe_and_returns_clean_dict():
    manager = BackgroundTaskManager()
    manager._lookup_trace_id_for_run = AsyncMock(return_value=None)
    session = SimpleNamespace(metadata={"trace_id": "trace-1", "agent_id": "agent-1"})

    info = await manager._build_run_info_from_session(
        session, session_id="s1", run_id="run-1", user_id="u1"
    )

    assert "_cancel_probe" not in info
    assert info["trace_id"] == "trace-1"
    stored = manager._run_info["run-1"]
    assert stored["_cancel_probe"] is True
    assert stored["session_id"] == "s1"
