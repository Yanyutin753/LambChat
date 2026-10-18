"""Scheduled runs outlive old wall-clock limits while retaining execution ownership."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def test_legacy_timeout_inputs_are_accepted_but_do_not_limit_execution():
    from src.kernel.schemas.scheduled_task import ScheduledTaskCreate, ScheduledTaskUpdate

    for seconds in (0, 3600, 864000):
        task = ScheduledTaskCreate(
            name="Long check",
            agent_id="quick",
            trigger_type="interval",
            trigger_config={"seconds": 3600},
            timeout_seconds=seconds,
        )
        assert task.timeout_seconds == 0
        assert ScheduledTaskUpdate(timeout_seconds=seconds).timeout_seconds == 0


async def test_standalone_monitor_waits_beyond_old_deadline_and_renews_lock():
    from src.infra.scheduler.runner import ScheduledTaskRunner
    from src.infra.task.status import TaskStatus

    manager = SimpleNamespace(
        get_run_status=AsyncMock(side_effect=[TaskStatus.RUNNING, TaskStatus.COMPLETED]),
        cancel_run=AsyncMock(),
    )
    with (
        patch("src.infra.scheduler.runner.asyncio.sleep", AsyncMock()),
        patch(
            "src.infra.scheduler.runner.extend_task_lock", AsyncMock(return_value=True), create=True
        ) as renew,
    ):
        result = await ScheduledTaskRunner()._wait_for_completion(
            manager, "chat", "run", "owner", task_id="task", lock_token="token"
        )
    assert result == {"session_status": "completed"}
    manager.cancel_run.assert_not_awaited()
    assert renew.await_count >= 1


async def test_old_conversation_run_is_not_cancelled_by_elapsed_time():
    from src.infra.scheduler.conversation import dispatch_pending

    record = {
        "_id": "run",
        "task_id": "task",
        "session_id": "chat",
        "owner_id": "owner",
        "conversation_state": "submitted",
        "timeout_seconds": 10,
        "started_at": datetime.now(timezone.utc) - timedelta(days=3),
    }
    storage = SimpleNamespace(
        pending_conversation_runs=AsyncMock(return_value=[record]),
        get_task=AsyncMock(return_value=SimpleNamespace()),
    )
    manager = SimpleNamespace(
        get_run_status=AsyncMock(return_value="running"), cancel_run=AsyncMock()
    )
    with (
        patch("src.infra.scheduler.runner.reconcile_standalone_finalizations", AsyncMock()),
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
        patch("src.infra.task.manager.get_task_manager", return_value=manager),
        patch("src.infra.scheduler.conversation._finish", AsyncMock()) as finish,
    ):
        await dispatch_pending()
    manager.cancel_run.assert_not_awaited()
    finish.assert_not_awaited()


async def test_arq_scheduled_function_has_no_deadline_but_other_jobs_keep_theirs():
    from src.infra.task.arq_runtime import EmbeddedArqRuntime
    from src.kernel.config import settings

    worker = EmbeddedArqRuntime()._create_worker()
    assert worker.job_timeout_s is None
    assert worker.functions["run_scheduled_agent_task"].timeout_s is None
    assert worker.functions["run_agent_task"].timeout_s == settings.ARQ_JOB_TIMEOUT_SECONDS
    assert worker.in_progress_timeout_s < float("inf")


@pytest.mark.parametrize("executor_key", ["conversation_schedule", "scheduled_agent_stream"])
async def test_scheduled_payload_ignores_total_watchdog(executor_key):
    from src.infra.task import arq_worker

    async def execute(**kwargs):
        await asyncio.sleep(0.02)
        return False

    executor = SimpleNamespace(
        run_task=AsyncMock(side_effect=execute), _update_session_status=AsyncMock()
    )
    manager = SimpleNamespace(_ensure_executor=lambda: executor, _tasks={}, _run_info={})
    store = SimpleNamespace(delete=AsyncMock())
    payload = {
        "session_id": "chat",
        "run_id": "run",
        "agent_id": "quick",
        "message": "check",
        "user_id": "owner",
        "executor_key": executor_key,
    }
    with (
        patch.object(arq_worker, "get_task_manager", return_value=manager),
        patch.object(arq_worker, "_resolve_executor", return_value=object()),
        patch.object(arq_worker, "_run_watchdog_timeout", return_value=0.001),
        patch.object(arq_worker, "_validate_standalone_scheduled_admission", AsyncMock()),
        patch.object(arq_worker, "_release_concurrency_slot", AsyncMock()),
    ):
        await arq_worker._run_agent_payload(store, payload, "dispatch", "run")
    executor._update_session_status.assert_not_awaited()
    store.delete.assert_awaited_once_with("dispatch")


async def test_scheduled_arq_job_refreshes_queue_ownership():
    from src.infra.task import arq_worker

    async def execute(*args):
        await asyncio.sleep(0.02)

    redis = SimpleNamespace(expire=AsyncMock(return_value=True))
    with (
        patch.object(arq_worker, "run_agent_task", execute),
        patch.object(arq_worker, "_SCHEDULED_RENEW_INTERVAL", 0.001, create=True),
    ):
        await arq_worker.run_scheduled_agent_task(
            {"redis": redis, "job_id": "dispatch"}, "dispatch"
        )
    assert redis.expire.await_count > 1
    assert any(call.args[0] == "arq:in-progress:dispatch" for call in redis.expire.await_args_list)


@pytest.mark.parametrize("renewal", [False, ConnectionError("Redis unavailable")])
async def test_standalone_lease_loss_cancels_existing_run_without_retry(renewal):
    from src.infra.scheduler.runner import ScheduledTaskRunner, _ExecutionLeaseLostError

    manager = SimpleNamespace(cancel_run=AsyncMock(), get_run_status=AsyncMock())
    renew = AsyncMock(
        **(
            {"side_effect": renewal}
            if isinstance(renewal, Exception)
            else {"return_value": renewal}
        )
    )
    with patch("src.infra.scheduler.runner.extend_task_lock", renew):
        with pytest.raises(_ExecutionLeaseLostError):
            await ScheduledTaskRunner()._wait_for_completion(
                manager, "chat", "run", "owner", task_id="task", lock_token="token"
            )
    manager.cancel_run.assert_awaited_once_with("run", user_id="owner")
    manager.get_run_status.assert_not_awaited()


async def test_standalone_scheduled_worker_uses_token_owned_execution_lease():
    from src.infra.task import arq_worker

    identities = []

    @asynccontextmanager
    async def lease(goal, run_id, *, background_identity):
        identities.append((run_id, background_identity))
        yield

    payload = {
        "executor_key": "scheduled_agent_stream",
        "run_id": "run",
        "user_id": "owner",
        "session_id": "chat",
    }
    with (
        patch("src.infra.goal_runtime.goal_run_lease", lease),
        patch("src.infra.goal_runtime.validate_goal_admission", AsyncMock()),
        patch.object(
            arq_worker, "_validate_standalone_scheduled_admission", AsyncMock(), create=True
        ),
        patch.object(arq_worker, "_run_agent_payload", AsyncMock()),
    ):
        await arq_worker.run_agent_task(
            {"payload_store": SimpleNamespace(load=AsyncMock(return_value=payload))}, "run"
        )
    assert identities == [("run", ("owner", "chat"))]


@pytest.mark.parametrize(
    "status,current_run",
    [
        ("cancelled", "run"),
        ("completed", "run"),
        ("expired", "run"),
        ("failed", "run"),
        ("queued", "replacement"),
    ],
)
async def test_queued_standalone_cannot_restart_cancelled_terminal_or_replaced_run(
    status, current_run
):
    from src.infra.goal_runtime import GoalRunAdmissionError
    from src.infra.task import arq_worker

    session = SimpleNamespace(
        user_id="owner", metadata={"task_status": status, "current_run_id": current_run}
    )
    manager = SimpleNamespace(
        storage=SimpleNamespace(get_by_session_id=AsyncMock(return_value=session))
    )
    with patch.object(arq_worker, "get_task_manager", return_value=manager):
        with pytest.raises(GoalRunAdmissionError):
            await arq_worker._validate_standalone_scheduled_admission(
                {"session_id": "chat", "user_id": "owner"}, "run"
            )


async def test_real_arq_scheduled_job_outlives_worker_deadline(monkeypatch, tmp_path):
    """Exercise ARQ's actual wait_for and Redis ownership, with a one-second limit."""
    import shutil
    import subprocess
    from pathlib import Path

    from arq import create_pool
    from arq.connections import RedisSettings

    from scripts.e2e_conversation_schedules import free_port, stop
    from src.infra.task import arq_worker
    from src.infra.task.arq_payloads import TaskArqPayloadStore, enqueue_scheduled_job
    from src.infra.task.arq_runtime import EmbeddedArqRuntime
    from src.kernel.config import settings

    binary = shutil.which("redis-server") or str(Path.home() / ".local/opt/redis/bin/redis-server")
    if not Path(binary).is_file():
        pytest.skip("Local redis-server is unavailable")
    port = free_port()
    with (tmp_path / "redis.log").open("w") as log:
        process = subprocess.Popen(
            [
                binary,
                "--bind",
                "127.0.0.1",
                "--port",
                str(port),
                "--save",
                "",
                "--appendonly",
                "no",
            ],
            stdout=log,
            stderr=log,
        )
        redis = worker = None
        try:
            redis = await create_pool(
                RedisSettings(host="127.0.0.1", port=port, conn_retry_delay=0.1),
                default_queue_name=settings.ARQ_QUEUE_NAME,
            )
            monkeypatch.setattr(settings, "REDIS_URL", f"redis://127.0.0.1:{port}/0")
            monkeypatch.setattr(settings, "REDIS_PASSWORD", "")
            monkeypatch.setattr(settings, "ARQ_JOB_TIMEOUT_SECONDS", 1)
            monkeypatch.setattr(settings, "ARQ_WORKER_MAX_JOBS", 1)

            async def execute(*_args):
                await asyncio.sleep(1.2)

            execute_mock = AsyncMock(side_effect=execute)
            monkeypatch.setattr(arq_worker, "run_agent_task", execute_mock)
            worker = EmbeddedArqRuntime()._create_worker()
            worker.cron_jobs = []
            worker.ctx["payload_store"] = TaskArqPayloadStore(redis)
            worker.burst = True
            await worker.ctx["payload_store"].save("run", {"executor_key": "conversation_schedule"})
            assert await enqueue_scheduled_job(redis, "run")
            assert not await enqueue_scheduled_job(redis, "run")
            assert await redis.ttl("arq:job:run") == -1
            assert await redis.ttl("task:arq:payload:run") == -1
            await asyncio.wait_for(worker.async_run(), 15)
            assert worker.jobs_complete == 1
            assert worker.jobs_failed == 0
            execute_mock.assert_awaited_once()
        finally:
            if worker is not None:
                await worker.close()
            if redis is not None:
                await redis.aclose()
            stop(process)
