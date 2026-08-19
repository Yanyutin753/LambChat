from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException

from src.api.routes import human
from src.infra.storage.mongodb import ApprovalResponse


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

    with pytest.raises(HTTPException) as exc:
        await human.respond_to_approval(
            "approval-1",
            approved=True,
            response="{}",
        )

    assert exc.value.status_code == 400
    assert notified == []


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
