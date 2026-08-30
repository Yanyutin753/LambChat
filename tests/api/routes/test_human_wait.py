from __future__ import annotations

import asyncio
import json

import pytest

from src.api.routes import human
from src.infra.storage.mongodb import ApprovalResponse
from src.kernel.errors import AppError


@pytest.mark.asyncio
async def test_wait_for_response_awaits_cancelled_distributed_wait_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_id = "approval-1"
    response = ApprovalResponse(approved=True, response={"ok": True})
    cleanup_started = asyncio.Event()
    cleanup_continue = asyncio.Event()
    cleanup_done = False

    class _FakeApprovalStorage:
        def __init__(self) -> None:
            self.get_response_calls = 0

        async def get_response(self, requested_id: str):
            assert requested_id == approval_id
            self.get_response_calls += 1
            if self.get_response_calls == 1:
                return None
            return response

    async def fake_distributed_wait(requested_id: str, timeout: float):
        nonlocal cleanup_done
        assert requested_id == approval_id
        assert timeout == 1
        try:
            await asyncio.sleep(60)
        finally:
            cleanup_started.set()
            await cleanup_continue.wait()
            cleanup_done = True

    event = asyncio.Event()
    human._local_events[approval_id] = (event, 0)
    monkeypatch.setattr(human, "_approval_storage", _FakeApprovalStorage())
    monkeypatch.setattr(human, "wait_for_response_distributed", fake_distributed_wait)

    wait_task = asyncio.create_task(human.wait_for_response(approval_id, timeout=1))
    await asyncio.sleep(0)
    event.set()
    await asyncio.wait_for(cleanup_started.wait(), timeout=1)

    assert wait_task.done() is False
    cleanup_continue.set()

    result = await wait_task

    assert result == response
    assert cleanup_done is True
    assert approval_id not in human._local_events


@pytest.mark.asyncio
async def test_respond_to_approval_offloads_response_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    updated: list[tuple[str, str, ApprovalResponse]] = []
    notified: list[tuple[str, ApprovalResponse]] = []

    class _FakeApproval:
        status = "pending"

    class _FakeApprovalStorage:
        async def get(self, approval_id: str):
            assert approval_id == "approval-1"
            return _FakeApproval()

        async def update_status(
            self,
            approval_id: str,
            status: str,
            approval_response: ApprovalResponse,
        ) -> None:
            updated.append((approval_id, status, approval_response))

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    async def fake_notify(approval_id: str, approval_response: ApprovalResponse) -> None:
        notified.append((approval_id, approval_response))

    monkeypatch.setattr(human, "_approval_storage", _FakeApprovalStorage())
    monkeypatch.setattr(human, "run_blocking_io", fake_run_blocking_io, raising=False)
    monkeypatch.setattr(human, "notify_approval_response", fake_notify)

    result = await human.respond_to_approval(
        "approval-1",
        approved=True,
        response='{"note": "ok"}',
    )

    assert calls == [json.loads]
    assert updated[0][2].response == {"note": "ok"}
    assert notified[0][1].response == {"note": "ok"}
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_respond_to_approval_uses_atomic_pending_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notified: list[tuple[str, ApprovalResponse]] = []

    class _FakeApproval:
        status = "pending"

    class _FakeApprovalStorage:
        async def get(self, approval_id: str):
            assert approval_id == "approval-1"
            return _FakeApproval()

        async def respond_if_pending(
            self,
            approval_id: str,
            status: str,
            approval_response: ApprovalResponse,
        ):
            assert approval_id == "approval-1"
            assert status == "approved"
            assert approval_response.approved is True
            return None

    async def fake_notify(approval_id: str, approval_response: ApprovalResponse) -> None:
        notified.append((approval_id, approval_response))

    monkeypatch.setattr(human, "_approval_storage", _FakeApprovalStorage())
    monkeypatch.setattr(human, "notify_approval_response", fake_notify)

    with pytest.raises(AppError) as exc:
        await human.respond_to_approval(
            "approval-1",
            approved=True,
            response="{}",
        )

    assert exc.value.error_code.code == "approval_already_handled"
    assert exc.value.http_status == 400
    assert notified == []


@pytest.mark.asyncio
async def test_interrupt_resume_failure_restores_pending_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    restored: list[tuple[str, str]] = []

    class _FakeApproval:
        id = "approval-1"
        status = "pending"
        session_id = "session-1"
        metadata = {"mode": "interrupt", "interrupt_id": "interrupt-a"}

    class _FakeApprovalStorage:
        async def get(self, approval_id: str):
            assert approval_id == "approval-1"
            return _FakeApproval()

        async def respond_if_pending(self, approval_id, status, approval_response):
            return _FakeApproval()

        async def restore_pending_if_status(self, approval_id: str, status: str):
            restored.append((approval_id, status))
            return True

    async def fake_submit(_approval, _resume_value):
        return {"submitted": False, "run_id": None, "message": "checkpoint unavailable"}

    async def fake_notify(_approval_id, _approval_response):
        return None

    monkeypatch.setattr(human, "_approval_storage", _FakeApprovalStorage())
    monkeypatch.setattr(human, "notify_approval_response", fake_notify)
    monkeypatch.setattr("src.infra.task.hitl.submit_hitl_resume_run", fake_submit)

    with pytest.raises(AppError) as exc:
        await human.respond_to_approval("approval-1", approved=True, response="{}")

    assert exc.value.error_code.code == "human_resume_submit_failed"
    assert exc.value.http_status == 503
    assert restored == [("approval-1", "approved")]


@pytest.mark.asyncio
async def test_interrupt_resume_success_skips_blocking_waiter_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notified = False

    class _FakeApproval:
        id = "approval-1"
        status = "pending"
        session_id = "session-1"
        metadata = {"mode": "interrupt", "interrupt_id": "interrupt-a"}

    class _FakeApprovalStorage:
        async def get(self, _approval_id: str):
            return _FakeApproval()

        async def respond_if_pending(self, _approval_id, _status, _response):
            return _FakeApproval()

        async def expire_after(self, _approval_id: str):
            return True

    async def fake_submit(_approval, _resume_value):
        return {"submitted": True, "run_id": "run-2", "message": "ok"}

    async def fake_notify(_approval_id, _approval_response):
        nonlocal notified
        notified = True

    monkeypatch.setattr(human, "_approval_storage", _FakeApprovalStorage())
    monkeypatch.setattr(human, "notify_approval_response", fake_notify)
    monkeypatch.setattr("src.infra.task.hitl.submit_hitl_resume_run", fake_submit)
    monkeypatch.setattr("src.infra.task.hitl.settings.HITL_MODE", "blocking")

    result = await human.respond_to_approval("approval-1", approved=True, response="{}")

    assert result["hitl_resume"]["submitted"] is True
    assert notified is False


@pytest.mark.asyncio
async def test_arq_interrupt_prepares_before_atomic_response_and_activates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    class _FakeApproval:
        id = "approval-1"
        status = "pending"
        session_id = "session-1"
        metadata = {"mode": "interrupt", "run_id": "run-1", "trace_id": "trace-1"}

    class _FakeApprovalStorage:
        async def get(self, _approval_id: str):
            return _FakeApproval()

        async def respond_if_pending_with_metadata(
            self, _approval_id, _status, _response, metadata_updates
        ):
            order.append("claim")
            assert metadata_updates["resume_attempt_id"].startswith("hitl-resume:approval-1:")
            return _FakeApproval()

        async def expire_after(self, _approval_id: str):
            return True

    async def fake_prepare(_approval, _resume_value, **kwargs):
        order.append("prepare")
        assert kwargs["prepare_only"] is True
        return {
            "submitted": True,
            "run_id": "run-1",
            "message": "ok",
            "resume_attempt_id": kwargs["resume_attempt_id"],
        }

    async def fake_activate(approval_id: str, attempt_id: str):
        order.append("activate")
        assert approval_id == "approval-1"
        assert attempt_id.startswith("hitl-resume:approval-1:")

    monkeypatch.setattr(human, "_approval_storage", _FakeApprovalStorage())
    monkeypatch.setattr("src.infra.task.hitl.submit_hitl_resume_run", fake_prepare)
    monkeypatch.setattr("src.infra.task.hitl.activate_hitl_resume_attempt", fake_activate)
    monkeypatch.setattr("src.infra.task.hitl.settings.TASK_BACKEND", "arq")

    result = await human.respond_to_approval("approval-1", approved=True, response="{}")

    assert result["hitl_resume"]["run_id"] == "run-1"
    assert order == ["prepare", "claim", "activate"]


@pytest.mark.asyncio
async def test_concurrent_arq_responses_activate_only_the_atomic_winner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeApproval:
        id = "approval-1"
        status = "pending"
        session_id = "session-1"
        metadata = {"mode": "interrupt", "run_id": "run-1", "trace_id": "trace-1"}

    class _FakeApprovalStorage:
        def __init__(self) -> None:
            self.claimed = False
            self.lock = asyncio.Lock()

        async def get(self, _approval_id: str):
            return _FakeApproval()

        async def respond_if_pending_with_metadata(
            self, _approval_id, _status, _response, _metadata_updates
        ):
            async with self.lock:
                if self.claimed:
                    return None
                self.claimed = True
                return _FakeApproval()

        async def expire_after(self, _approval_id: str):
            return True

    prepare_count = 0
    both_prepared = asyncio.Event()
    activated: list[str] = []

    async def fake_prepare(_approval, _resume_value, **kwargs):
        nonlocal prepare_count
        prepare_count += 1
        if prepare_count == 2:
            both_prepared.set()
        await both_prepared.wait()
        return {
            "submitted": True,
            "run_id": "run-1",
            "message": "ok",
            "resume_attempt_id": kwargs["resume_attempt_id"],
        }

    async def fake_activate(_approval_id: str, attempt_id: str):
        activated.append(attempt_id)

    monkeypatch.setattr(human, "_approval_storage", _FakeApprovalStorage())
    monkeypatch.setattr("src.infra.task.hitl.submit_hitl_resume_run", fake_prepare)
    monkeypatch.setattr("src.infra.task.hitl.activate_hitl_resume_attempt", fake_activate)
    monkeypatch.setattr("src.infra.task.hitl.settings.TASK_BACKEND", "arq")

    results = await asyncio.gather(
        human.respond_to_approval("approval-1", approved=True, response='{"choice":"a"}'),
        human.respond_to_approval("approval-1", approved=False, response="{}"),
        return_exceptions=True,
    )

    successes = [result for result in results if isinstance(result, dict)]
    conflicts = [result for result in results if isinstance(result, AppError)]
    assert len(successes) == 1
    assert len(conflicts) == 1
    assert conflicts[0].error_code.code == "approval_already_handled"
    assert conflicts[0].http_status == 400
    assert prepare_count == 2
    assert len(activated) == 1


@pytest.mark.asyncio
async def test_create_approval_bounded_local_event_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    human._local_events.clear()
    previous_limit = human.HUMAN_LOCAL_EVENT_CACHE_MAX_ENTRIES
    monkeypatch.setattr(human, "HUMAN_LOCAL_EVENT_CACHE_MAX_ENTRIES", 2)

    created_ids: list[str] = []

    class _FakeApprovalStorage:
        async def create(self, approval, ttl=3600):
            created_ids.append(approval.id)
            return approval

    async def fake_notify_approval_created(_: str) -> None:
        return None

    monkeypatch.setattr(human, "_approval_storage", _FakeApprovalStorage())
    monkeypatch.setattr(human, "_notify_approval_created", fake_notify_approval_created)

    try:
        for index in range(3):
            approval = await human.create_approval(
                f"message-{index}",
                session_id=f"session-{index}",
                user_id="user-1",
            )
            assert approval.id == created_ids[index]

        assert len(human._local_events) == 2
        assert created_ids[0] not in human._local_events
    finally:
        monkeypatch.setattr(
            human,
            "HUMAN_LOCAL_EVENT_CACHE_MAX_ENTRIES",
            previous_limit,
        )
        human._local_events.clear()


@pytest.mark.asyncio
async def test_wait_for_response_cancels_distributed_wait_on_external_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """External cancellation must still clean up the distributed wait task.

    Regression test for issue #197: cleanup lived inside the try block, so a
    CancelledError from the outer MCPToolWithRetry wait_for skipped it and
    orphaned the wait tasks ("Task exception was never retrieved").
    """
    import contextlib

    approval_id = "approval-ext-cancel"
    distributed_cancelled = asyncio.Event()

    class _FakeApprovalStorage:
        async def get_response(self, _requested_id: str):
            return None

    async def tracked_distributed(_requested_id: str, _timeout: float):
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            distributed_cancelled.set()
            raise

    event = asyncio.Event()  # never set → both waits block until cancelled
    human._local_events[approval_id] = (event, 0)
    monkeypatch.setattr(human, "_approval_storage", _FakeApprovalStorage())
    monkeypatch.setattr(human, "wait_for_response_distributed", tracked_distributed)

    wait_task = asyncio.create_task(human.wait_for_response(approval_id, timeout=60))
    await asyncio.sleep(0.05)  # let it reach asyncio.wait
    wait_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await wait_task

    # finally-cleanup must have cancelled the distributed waiter.
    await asyncio.wait_for(distributed_cancelled.wait(), timeout=1)
    assert distributed_cancelled.is_set()
    human._local_events.pop(approval_id, None)
