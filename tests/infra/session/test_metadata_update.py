from __future__ import annotations

import pytest

from src.infra.session.manager import SessionManager
from src.infra.session.storage import SessionStorage


class _UpdateResult:
    matched_count = 1


class _FakeCollection:
    def __init__(self) -> None:
        self.update_one_calls: list[tuple[dict, dict]] = []
        self.find_one_and_update_called = False

    async def update_one(self, query: dict, update: dict) -> _UpdateResult:
        self.update_one_calls.append((query, update))
        return _UpdateResult()

    async def find_one_and_update(self, *_args, **_kwargs):
        self.find_one_and_update_called = True
        raise AssertionError("metadata-only updates should not fetch the full session document")


@pytest.mark.asyncio
async def test_update_metadata_only_uses_update_one_without_fetching_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_ensure_indexes(_self) -> None:
        return None

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", fake_ensure_indexes)
    storage = SessionStorage()
    collection = _FakeCollection()
    storage._collection = collection

    updated = await storage.update_metadata_only(
        "session-1",
        {"current_run_id": "run-1", "agent_id": "search"},
    )

    assert updated is True
    assert collection.find_one_and_update_called is False
    assert collection.update_one_calls
    query, update = collection.update_one_calls[0]
    assert query == {"session_id": "session-1"}
    assert update["$set"]["metadata.current_run_id"] == "run-1"
    assert update["$set"]["metadata.agent_id"] == "search"


@pytest.mark.asyncio
async def test_session_manager_get_session_events_forwards_limit_as_max_events() -> None:
    calls: list[tuple] = []

    class _FakeTraceStorage:
        async def get_session_events(self, *args, **kwargs):
            calls.append((args, kwargs))
            return [{"event_type": "done"}]

    manager = SessionManager()
    manager._trace_storage = _FakeTraceStorage()

    events = await manager.get_session_events("session-1", limit=25)

    assert events == [{"event_type": "done"}]
    assert calls == [(("session-1",), {"max_events": 25})]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"task_status": "running"}, True),
        ({"task_status": "failed", "task_recoverable": True}, True),
        ({"task_status": "completed"}, False),
        ({"task_status": "cancelled"}, False),
        ({"task_status": "waiting_human"}, False),
        ({"task_status": "failed", "task_recoverable": False}, False),
        ({"task_status": "running", "verification_required": True}, False),
        ({"task_status": "running", "task_error_code": "cancelled"}, False),
        ({"task_status": "running", "current_run_id": "new-run"}, False),
    ],
)
async def test_recovery_claim_mongo_predicate_preserves_terminal_and_run_owner(
    monkeypatch, metadata, expected
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.infra.session.session_run_metadata import SessionRunMetadataMixin

    document = {"_id": "canonical-id", "metadata": {"current_run_id": "run-1", **metadata}}

    def matches(query):
        for key, condition in query.items():
            if key == "$or":
                if not any(matches(branch) for branch in condition):
                    return False
                continue
            value = (
                document["_id"]
                if key == "_id"
                else document["metadata"].get(key.removeprefix("metadata."))
            )
            if isinstance(condition, dict):
                if "$in" in condition and value not in condition["$in"]:
                    return False
                if "$nin" in condition and value in condition["$nin"]:
                    return False
                if "$ne" in condition and value == condition["$ne"]:
                    return False
            elif value != condition:
                return False
        return True

    async def update_one(query, update):
        assert query["_id"] == "canonical-id"
        assert query["metadata.current_run_id"] == "run-1"
        assert query["metadata.verification_required"] == {"$ne": True}
        assert query["metadata.task_error_code"] == {
            "$nin": ["cancelled", "task_recovery_uncertain_effect"]
        }
        assert query["$or"] == [
            {
                "metadata.task_status": {
                    "$in": ["running", "starting", "recovering", "pending", "queued"]
                }
            },
            {"metadata.task_status": "failed", "metadata.task_recoverable": True},
        ]
        matched = matches(query)
        if matched:
            document["metadata"].update(
                {
                    key.removeprefix("metadata."): value
                    for key, value in update["$set"].items()
                    if key.startswith("metadata.")
                }
            )
        return SimpleNamespace(matched_count=int(matched))

    storage = SessionRunMetadataMixin()
    storage.ensure_indexes_if_needed = AsyncMock()
    storage._find_doc = AsyncMock(return_value={"_id": "canonical-id"})
    storage.collection = SimpleNamespace(update_one=update_one)
    previous = dict(document["metadata"])

    assert (
        await storage.claim_run_recovery(
            "object-id-session", "run-1", {"task_status": "recovering"}
        )
        is expected
    )
    assert document["metadata"] == (
        {**previous, "task_status": "recovering"} if expected else previous
    )


@pytest.mark.asyncio
async def test_recovery_followup_metadata_requires_same_run_and_nonterminal_status():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.infra.session.session_run_metadata import SessionRunMetadataMixin

    storage = SessionRunMetadataMixin()
    storage.ensure_indexes_if_needed = AsyncMock()
    storage._find_doc = AsyncMock(return_value={"_id": "canonical-id"})
    update = AsyncMock(return_value=SimpleNamespace(matched_count=0))
    storage.collection = SimpleNamespace(update_one=update)

    assert (
        await storage.update_metadata_for_run(
            "session-1",
            "run-1",
            {"task_status": "failed"},
            expected_statuses=["recovering", "pending", "queued", "starting"],
        )
        is False
    )
    query = update.await_args.args[0]
    assert query == {
        "_id": "canonical-id",
        "metadata.current_run_id": "run-1",
        "metadata.task_status": {"$in": ["recovering", "pending", "queued", "starting"]},
    }
