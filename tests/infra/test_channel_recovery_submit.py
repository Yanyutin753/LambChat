"""Channel reconnect reattaches to the original task rather than re-running input."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


async def test_replayed_message_reuses_persisted_run(monkeypatch, durable_state):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import submit_channel_task

    durable_state.events = [{"event_type": "done", "trace_id": "trace", "data": {}}]
    checkpoint = {
        "run_id": "original",
        "session_id": "original-session",
        "submitted": True,
        "trace_id": "trace",
    }
    context = SimpleNamespace(checkpoint=checkpoint, save=AsyncMock())
    token = current_delivery.set(context)
    manager = SimpleNamespace(submit=AsyncMock(), submit_arq=AsyncMock())
    try:
        result = await submit_channel_task(manager, session_id="new-session", user_id="u")
        assert result == ("original", "trace")
        manager.submit.assert_not_awaited()
        manager.submit_arq.assert_not_awaited()
    finally:
        current_delivery.reset(token)


async def test_disconnected_reply_stream_is_retried_not_completed(monkeypatch, durable_state):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import read_channel_events

    async def events(*args):
        yield {"event_type": "message:chunk", "data": {"content": "partial"}}

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: SimpleNamespace(read_from_redis=events),
    )
    token = current_delivery.set(SimpleNamespace(checkpoint={}))
    try:
        with pytest.raises(RuntimeError, match="ended"):
            [event async for event in read_channel_events("s", "r")]
    finally:
        current_delivery.reset(token)


async def test_completed_replay_ignores_terminal_events_before_last_resume(monkeypatch):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import read_channel_events

    events = [
        {"event_type": "message:chunk", "data": {"content": "old"}},
        {"event_type": "error", "data": {"code": "server_restart"}},
        {"event_type": "run:resumed", "data": {}},
        {"event_type": "message:chunk", "data": {"content": "final"}},
        {"event_type": "done", "data": {}},
    ]
    monkeypatch.setattr(
        "src.infra.session.trace_storage.get_trace_storage",
        lambda: SimpleNamespace(get_session_events=AsyncMock(return_value=events)),
    )
    token = current_delivery.set(SimpleNamespace(checkpoint={"reattached": True}))
    try:
        result = [event async for event in read_channel_events("s", "r")]
        assert result == events[2:]
    finally:
        current_delivery.reset(token)


async def test_run_identity_is_checkpointed_before_submission(monkeypatch):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import submit_channel_task
    from src.kernel.config import settings

    checkpoint = {}

    async def save(**values):
        checkpoint.update(values)

    async def submit(**kwargs):
        assert checkpoint["run_id"] == kwargs["run_id"]
        assert checkpoint["session_id"] == kwargs["session_id"]
        assert kwargs["write_user_message_immediately"]
        return kwargs["run_id"], "trace"

    monkeypatch.setattr(settings, "TASK_BACKEND", "local")
    manager = SimpleNamespace(submit=AsyncMock(side_effect=submit))
    token = current_delivery.set(SimpleNamespace(checkpoint=checkpoint, save=save))
    try:
        result = await submit_channel_task(manager, session_id="session", user_id="u")
        assert result[0] == checkpoint["run_id"]
        assert checkpoint["submitted"]
    finally:
        current_delivery.reset(token)


@pytest.fixture
def durable_state(monkeypatch):
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TASK_BACKEND", "local")
    state = SimpleNamespace(events=[], metadata={}, payload=None, job_status="not_found")
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: SimpleNamespace(
            get_session=AsyncMock(
                side_effect=lambda _: SimpleNamespace(id="s", metadata=state.metadata)
            )
        ),
    )
    monkeypatch.setattr(
        "src.infra.session.trace_storage.get_trace_storage",
        lambda: SimpleNamespace(
            get_session_events=AsyncMock(side_effect=lambda *args, **kwargs: state.events)
        ),
    )
    monkeypatch.setattr(
        "src.infra.task.heartbeat.TaskHeartbeat.is_stale", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(
        "src.infra.task.arq_payloads.TaskArqPayloadStore.load",
        AsyncMock(side_effect=lambda _: state.payload),
    )
    monkeypatch.setattr("arq.jobs.Job.status", AsyncMock(side_effect=lambda: state.job_status))
    return state


@pytest.mark.parametrize("backend", ["local", "arq"])
@pytest.mark.parametrize("persisted_user", [False, True])
async def test_retry_dispatches_same_run_after_metadata_only_failure(
    monkeypatch, durable_state, backend, persisted_user
):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import submit_channel_task
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TASK_BACKEND", backend)
    checkpoint = {}
    calls = []

    async def save(**values):
        checkpoint.update(values)

    async def submit(**kwargs):
        calls.append(kwargs)
        durable_state.metadata["current_run_id"] = kwargs["run_id"]
        if len(calls) == 1:
            if persisted_user:
                durable_state.events.append(
                    {"event_type": "user:message", "trace_id": "t", "data": {}}
                )
            raise RuntimeError("crashed after metadata")
        return kwargs["run_id"], "t"

    manager = SimpleNamespace(
        submit=AsyncMock(side_effect=submit),
        submit_arq=AsyncMock(side_effect=submit),
        _get_arq_pool=AsyncMock(return_value=SimpleNamespace()),
    )
    token = current_delivery.set(SimpleNamespace(checkpoint=checkpoint, save=save))
    try:
        with pytest.raises(RuntimeError, match="crashed"):
            await submit_channel_task(manager, session_id="s", user_id="u")
        result = await submit_channel_task(manager, session_id="ignored", user_id="u")
        assert len(calls) == 2
        assert calls[0]["run_id"] == calls[1]["run_id"] == result[0]
        assert calls[1].get("user_message_written", False) is persisted_user
        if persisted_user:
            assert calls[1]["trace_id"] == "t"
    finally:
        current_delivery.reset(token)


async def test_recoverable_error_is_not_acknowledged(monkeypatch, durable_state):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import read_channel_events

    durable_state.events = [{"event_type": "error", "data": {"code": "server_restart"}}]
    durable_state.metadata = {"current_run_id": "r", "task_recoverable": True}
    manager = SimpleNamespace(_resume_interrupted_run=AsyncMock(return_value={"success": True}))
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: manager)
    token = current_delivery.set(SimpleNamespace(checkpoint={"reattached": True}))
    try:
        with pytest.raises(RuntimeError, match="recover"):
            [event async for event in read_channel_events("s", "r")]
        manager._resume_interrupted_run.assert_awaited_once()
    finally:
        current_delivery.reset(token)


async def test_saved_arq_payload_reenqueues_original_job_without_resubmission(
    monkeypatch, durable_state
):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import submit_channel_task
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TASK_BACKEND", "arq")
    durable_state.payload = {"run_id": "r", "trace_id": "t", "message": "original"}
    pool = SimpleNamespace(enqueue_job=AsyncMock())
    manager = SimpleNamespace(_get_arq_pool=AsyncMock(return_value=pool), submit_arq=AsyncMock())
    token = current_delivery.set(
        SimpleNamespace(checkpoint={"run_id": "r", "session_id": "s"}, save=AsyncMock())
    )
    try:
        assert await submit_channel_task(manager, session_id="s") == ("r", "t")
        pool.enqueue_job.assert_awaited_once_with("run_agent_task", "r", _job_id="r")
        manager.submit_arq.assert_not_awaited()
    finally:
        current_delivery.reset(token)


async def test_live_local_task_reattaches_even_before_heartbeat(monkeypatch, durable_state):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import submit_channel_task
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TASK_BACKEND", "local")
    manager = SimpleNamespace(_tasks={"r": SimpleNamespace(done=lambda: False)}, submit=AsyncMock())
    token = current_delivery.set(
        SimpleNamespace(checkpoint={"run_id": "r", "session_id": "s"}, save=AsyncMock())
    )
    try:
        assert await submit_channel_task(manager, session_id="s") == ("r", "")
        manager.submit.assert_not_awaited()
    finally:
        current_delivery.reset(token)


async def test_reattached_orphan_is_recovered_before_blocking_stream(monkeypatch, durable_state):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import read_channel_events
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TASK_BACKEND", "local")
    durable_state.events = [{"event_type": "message:chunk", "data": {"content": "partial"}}]
    durable_state.metadata = {"current_run_id": "r", "task_status": "running"}
    manager = SimpleNamespace(_resume_interrupted_run=AsyncMock(return_value={"success": True}))
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: manager)

    async def unread(*args):
        raise AssertionError("must recover before opening blocking stream")
        yield

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: SimpleNamespace(read_from_redis=unread),
    )
    token = current_delivery.set(SimpleNamespace(checkpoint={"reattached": True}))
    try:
        with pytest.raises(RuntimeError, match="recover"):
            [event async for event in read_channel_events("s", "r")]
        manager._resume_interrupted_run.assert_awaited_once()
    finally:
        current_delivery.reset(token)


async def test_fresh_remote_heartbeat_prevents_duplicate_dispatch(monkeypatch, durable_state):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import submit_channel_task

    monkeypatch.setattr(
        "src.infra.task.heartbeat.TaskHeartbeat.is_stale", AsyncMock(return_value=False)
    )
    manager = SimpleNamespace(submit=AsyncMock())
    token = current_delivery.set(
        SimpleNamespace(checkpoint={"run_id": "r", "session_id": "s"}, save=AsyncMock())
    )
    try:
        assert await submit_channel_task(manager, session_id="s") == ("r", "")
        manager.submit.assert_not_awaited()
    finally:
        current_delivery.reset(token)


async def test_recoverable_error_waits_for_fresh_executor(monkeypatch, durable_state):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import read_channel_events

    durable_state.events = [{"event_type": "error", "data": {"code": "server_restart"}}]
    durable_state.metadata = {"current_run_id": "r", "task_recoverable": True}
    monkeypatch.setattr(
        "src.infra.task.heartbeat.TaskHeartbeat.is_stale", AsyncMock(return_value=False)
    )
    manager = SimpleNamespace(_resume_interrupted_run=AsyncMock())
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: manager)
    token = current_delivery.set(SimpleNamespace(checkpoint={"reattached": True}))
    try:
        with pytest.raises(RuntimeError, match="recover"):
            [event async for event in read_channel_events("s", "r")]
        manager._resume_interrupted_run.assert_not_awaited()
    finally:
        current_delivery.reset(token)


async def test_waiting_human_run_is_not_automatically_resumed(monkeypatch, durable_state):
    from src.infra.channel.recovery import _recover_channel_run

    durable_state.metadata = {"current_run_id": "r", "task_status": "waiting_human"}
    manager = SimpleNamespace(_resume_interrupted_run=AsyncMock())
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: manager)
    assert not await _recover_channel_run("s", "r", error=False)
    manager._resume_interrupted_run.assert_not_awaited()


@pytest.mark.parametrize("backend", ["local", "arq"])
@pytest.mark.parametrize("pregraph_event", [None, "metadata", "goal:start"])
async def test_submitted_checkpoint_without_execution_dispatches_original_input(
    monkeypatch, durable_state, backend, pregraph_event
):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import submit_channel_task
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TASK_BACKEND", backend)
    durable_state.events = [
        {"event_type": "user:message", "trace_id": "t", "data": {"content": "original input"}}
    ]
    if pregraph_event:
        durable_state.events.append({"event_type": pregraph_event, "trace_id": "t", "data": {}})
    durable_state.metadata = {"current_run_id": "r", "task_status": "pending"}
    checkpoint = {"run_id": "r", "session_id": "s", "submitted": True, "trace_id": "t"}

    async def save(**values):
        checkpoint.update(values)

    manager = SimpleNamespace(
        submit=AsyncMock(return_value=("r", "t")),
        submit_arq=AsyncMock(return_value=("r", "t")),
        _get_arq_pool=AsyncMock(return_value=SimpleNamespace()),
    )
    token = current_delivery.set(SimpleNamespace(checkpoint=checkpoint, save=save))
    try:
        assert await submit_channel_task(
            manager, session_id="ignored", message="original input", executor=object()
        ) == ("r", "t")
        submit = manager.submit_arq if backend == "arq" else manager.submit
        submit.assert_awaited_once()
        kwargs = submit.await_args.kwargs
        assert kwargs["session_id"] == "s"
        assert kwargs["run_id"] == "r"
        assert kwargs["trace_id"] == "t"
        assert kwargs["message"] == "original input"
        assert kwargs["user_message_written"] is True
        assert not kwargs.get("interrupted_resume")
    finally:
        current_delivery.reset(token)


@pytest.mark.parametrize("status", ["waiting_human", "completed", "cancelled"])
async def test_submitted_inactive_terminal_or_waiting_run_is_not_redispatched(
    monkeypatch, durable_state, status
):
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.recovery import submit_channel_task

    durable_state.metadata = {"current_run_id": "r", "task_status": status}
    manager = SimpleNamespace(submit=AsyncMock())
    token = current_delivery.set(
        SimpleNamespace(
            checkpoint={"submitted": True, "run_id": "r", "session_id": "s", "trace_id": "t"},
            save=AsyncMock(),
        )
    )
    try:
        assert await submit_channel_task(manager, session_id="s", message="original") == ("r", "t")
        manager.submit.assert_not_awaited()
    finally:
        current_delivery.reset(token)
