from __future__ import annotations

import json

import pytest

from src.infra.storage import mongodb
from src.infra.storage.mongodb import ApprovalResponse, ApprovalStorage, MongoDBStorage


class _FakeCursor:
    def __init__(self, docs: list[dict[str, str]]) -> None:
        self._docs = docs
        self.limit_value: int | None = None

    def limit(self, value: int):
        self.limit_value = value
        return self

    async def __aiter__(self):
        docs = self._docs if self.limit_value is None else self._docs[: self.limit_value]
        for doc in docs:
            yield doc


class _FakeCollection:
    def __init__(self, docs: list[dict[str, str]]) -> None:
        self.docs = docs
        self.find_calls: list[tuple[dict, dict | None]] = []
        self.last_cursor: _FakeCursor | None = None

    def find(self, query: dict, projection: dict | None = None):
        self.find_calls.append((query, projection))
        self.last_cursor = _FakeCursor(self.docs)
        return self.last_cursor


class _FakeApprovalCursor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs
        self.limit_value: int | None = None

    def sort(self, field: str, direction: int):
        assert (field, direction) == ("created_at", -1)
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def __aiter__(self):
        self._iter = iter(
            self._docs if self.limit_value is None else self._docs[: self.limit_value]
        )
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeApprovalCollection:
    def __init__(self, docs: list[dict]) -> None:
        self.docs = docs
        self.cursor: _FakeApprovalCursor | None = None
        self.find_calls: list[dict] = []

    def find(self, query: dict):
        self.find_calls.append(query)
        self.cursor = _FakeApprovalCursor(self.docs)
        return self.cursor


@pytest.mark.asyncio
async def test_mongodb_storage_keys_uses_projection_anchored_regex_and_limit() -> None:
    storage = MongoDBStorage()
    collection = _FakeCollection([{"_id": f"task:{index}"} for index in range(2000)])
    storage._collection = collection

    keys = await storage.keys("task:*")

    assert len(keys) == 1000
    assert keys[0] == "task:0"
    assert keys[-1] == "task:999"
    assert collection.find_calls[0][1] == {"_id": 1}
    regex = collection.find_calls[0][0]["_id"]["$regex"]
    assert regex.startswith("(?s:task:")
    assert regex.endswith("\\Z")
    assert collection.last_cursor is not None
    assert collection.last_cursor.limit_value == 1000


@pytest.mark.asyncio
async def test_approval_storage_list_pending_applies_default_limit() -> None:
    storage = ApprovalStorage()
    collection = _FakeApprovalCollection(
        [
            {
                "id": f"approval-{index}",
                "message": "ok",
                "type": "form",
                "fields": [],
                "status": "pending",
                "created_at": None,
                "expires_at": None,
                "extensions": 0,
            }
            for index in range(150)
        ]
    )
    storage._collection = collection
    storage._indexes_created = True

    approvals = await storage.list_pending(user_id="user-1")

    assert len(approvals) == 100
    assert collection.cursor is not None
    assert collection.cursor.limit_value == 100


class _RespondCollection:
    """Fake collection capturing find_one_and_update calls."""

    def __init__(self, *, return_doc: dict | None) -> None:
        self._return_doc = return_doc
        self.calls: list[tuple[dict, dict, dict | None, object | None]] = []

    async def find_one_and_update(
        self,
        filter_doc: dict,
        update_doc: dict,
        projection: dict | None = None,
        return_document: object | None = None,
    ):
        self.calls.append((filter_doc, update_doc, projection, return_document))
        if self._return_doc is None:
            return None
        return dict(self._return_doc)


@pytest.mark.asyncio
async def test_respond_if_pending_returns_updated_approval() -> None:
    from pymongo import ReturnDocument

    storage = ApprovalStorage()
    collection = _RespondCollection(
        return_doc={"id": "approval-1", "message": "请确认", "status": "approved"}
    )
    storage._collection = collection
    storage._indexes_created = True

    response = ApprovalResponse(approved=True, response={"ok": True})
    result = await storage.respond_if_pending("approval-1", "approved", response)

    assert result is not None
    assert result.id == "approval-1"
    assert result.status == "approved"

    filter_doc, update_doc, projection, return_document = collection.calls[0]
    # Only a still-pending, unexpired approval may be claimed atomically.
    # Interrupt-mode approvals carry no expires_at and remain claimable.
    assert filter_doc["_id"] == "approval-1"
    assert filter_doc["status"] == "pending"
    expiry_clauses = filter_doc["$or"]
    assert {"expires_at": None} in expiry_clauses
    future_clauses = [c for c in expiry_clauses if c != {"expires_at": None}]
    assert len(future_clauses) == 1
    assert "$gt" in future_clauses[0]["expires_at"]
    assert update_doc["$set"]["status"] == "approved"
    assert update_doc["$set"]["response"] == response.model_dump()
    assert projection == {"response": 0}
    assert return_document == ReturnDocument.AFTER


@pytest.mark.asyncio
async def test_respond_if_pending_returns_none_when_already_handled_or_expired() -> None:
    storage = ApprovalStorage()
    collection = _RespondCollection(return_doc=None)
    storage._collection = collection
    storage._indexes_created = True

    response = ApprovalResponse(approved=False, response={})
    result = await storage.respond_if_pending("approval-1", "rejected", response)

    assert result is None
    filter_doc, _update_doc, _projection, _return_document = collection.calls[0]
    # The atomic guard rejects already-responded or expired approvals by
    # requiring pending status plus a future expiry (or no expiry at all,
    # which is the interrupt-mode no-timeout contract).
    assert set(filter_doc.keys()) == {"_id", "status", "$or"}
    assert filter_doc["_id"] == "approval-1"
    assert filter_doc["status"] == "pending"
    assert {"expires_at": None} in filter_doc["$or"]


@pytest.mark.asyncio
async def test_respond_if_pending_records_resume_attempt_atomically() -> None:
    storage = ApprovalStorage()
    collection = _RespondCollection(
        return_doc={
            "id": "approval-1",
            "message": "请确认",
            "status": "approved",
            "metadata": {"mode": "interrupt", "resume_attempt_id": "attempt-1"},
        }
    )
    storage._collection = collection
    storage._indexes_created = True

    response = ApprovalResponse(approved=True, response={})
    result = await storage.respond_if_pending_with_metadata(
        "approval-1",
        "approved",
        response,
        {"resume_attempt_id": "attempt-1"},
    )

    assert result is not None
    update_doc = collection.calls[0][1]
    assert update_doc["$set"]["metadata.resume_attempt_id"] == "attempt-1"


@pytest.mark.asyncio
async def test_restore_pending_if_status_removes_failed_response() -> None:
    storage = ApprovalStorage()
    collection = _RespondCollection(return_doc={"id": "approval-1"})
    storage._collection = collection
    storage._indexes_created = True

    restored = await storage.restore_pending_if_status("approval-1", "approved")

    assert restored is True
    filter_doc, update_doc, _projection, _return_document = collection.calls[0]
    assert filter_doc == {"_id": "approval-1", "status": "approved"}
    assert update_doc["$set"]["status"] == "pending"
    assert update_doc["$unset"] == {"response": "", "updated_at": ""}


def test_close_approval_storage_releases_cached_singleton() -> None:
    storage = mongodb.get_approval_storage()

    mongodb.close_approval_storage()

    assert mongodb.get_approval_storage.cache_info().currsize == 0
    assert mongodb.get_approval_storage() is not storage
    mongodb.close_approval_storage()


def test_close_approval_storage_does_not_create_singleton_when_unused() -> None:
    mongodb.get_approval_storage.cache_clear()

    mongodb.close_approval_storage()

    assert mongodb.get_approval_storage.cache_info().currsize == 0


@pytest.mark.asyncio
async def test_wait_for_response_distributed_returns_on_pubsub_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = ApprovalResponse(approved=True, response={"ok": True})
    subscribed: dict[str, object] = {}

    class _FakeStorage:
        def __init__(self) -> None:
            self.has_response_calls = 0
            self.get_response_calls = 0

        async def has_response(self, approval_id: str) -> bool:
            assert approval_id == "approval-1"
            self.has_response_calls += 1
            return False

        async def get_response(self, approval_id: str):
            assert approval_id == "approval-1"
            self.get_response_calls += 1
            return response

    class _FakeHub:
        def __init__(self) -> None:
            self.handler = None

        def subscribe(self, channel: str, handler):
            subscribed["channel"] = channel
            self.handler = handler
            return "token-1"

        def unsubscribe(self, token: str) -> None:
            subscribed["unsubscribed"] = token

        async def start(self) -> None:
            subscribed["started"] = True
            assert self.handler is not None
            await self.handler({"data": '{"approval_id": "approval-1"}'})

        async def stop_if_idle(self) -> None:
            subscribed["stopped_if_idle"] = True

    storage = _FakeStorage()
    monkeypatch.setattr(mongodb, "get_approval_storage", lambda: storage)
    monkeypatch.setattr(mongodb, "get_pubsub_hub", lambda: _FakeHub(), raising=False)

    result = await mongodb.wait_for_response_distributed("approval-1", timeout=1)

    assert result == response
    assert subscribed["channel"] == mongodb.APPROVAL_RESPONSE_CHANNEL
    assert subscribed["unsubscribed"] == "token-1"
    assert subscribed["stopped_if_idle"] is True
    assert storage.get_response_calls == 1


@pytest.mark.asyncio
async def test_wait_for_response_distributed_offloads_notification_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = ApprovalResponse(approved=True, response={"ok": True})
    calls = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    class _FakeStorage:
        async def has_response(self, _approval_id: str) -> bool:
            return False

        async def get_response(self, _approval_id: str):
            return response

    class _FakeHub:
        def __init__(self) -> None:
            self.handler = None

        def subscribe(self, _channel: str, handler):
            self.handler = handler
            return "token-1"

        def unsubscribe(self, _token: str) -> None:
            return None

        async def start(self) -> None:
            assert self.handler is not None
            await self.handler({"data": '{"approval_id": "approval-1"}'})

        async def stop_if_idle(self) -> None:
            return None

    monkeypatch.setattr(mongodb, "get_approval_storage", lambda: _FakeStorage())
    monkeypatch.setattr(mongodb, "get_pubsub_hub", lambda: _FakeHub(), raising=False)
    monkeypatch.setattr(mongodb, "run_blocking_io", fake_run_blocking_io)

    result = await mongodb.wait_for_response_distributed("approval-1", timeout=1)

    assert result == response
    assert calls == [json.loads]


@pytest.mark.asyncio
async def test_notify_approval_response_publishes_approval_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[tuple[str, str]] = []

    class _FakeRedis:
        async def publish(self, channel: str, payload: str) -> int:
            published.append((channel, payload))
            return 1

    monkeypatch.setattr(mongodb, "get_redis_client", lambda: _FakeRedis())

    await mongodb.notify_approval_response(
        "approval-1",
        ApprovalResponse(approved=True, response={"ok": True}),
    )

    assert published == [
        (
            mongodb.APPROVAL_RESPONSE_CHANNEL,
            '{"approval_id": "approval-1"}',
        )
    ]


@pytest.mark.asyncio
async def test_notify_approval_response_offloads_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    published: list[tuple[str, str]] = []
    calls = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    class _FakeRedis:
        async def publish(self, channel: str, payload: str) -> int:
            published.append((channel, payload))
            return 1

    monkeypatch.setattr(mongodb, "get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(mongodb, "run_blocking_io", fake_run_blocking_io)

    await mongodb.notify_approval_response(
        "approval-1",
        ApprovalResponse(approved=True, response={"ok": True}),
    )

    assert calls == [json.dumps]
    assert published[0][0] == mongodb.APPROVAL_RESPONSE_CHANNEL
