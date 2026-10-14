import sys
from types import SimpleNamespace

import pytest

from src.infra.storage import mongodb
from tests.api.routes.test_session_runs import _load_session_routes_module


class _ApprovalCollection:
    def __init__(self, docs):
        self.docs = docs
        self.calls = []

    def find(self, query, projection):
        self.calls.append((query, projection))
        ids = query["_id"]["$in"]
        now = query["$or"][0]["expires_at"]["$gt"]
        docs = [
            dict(doc)
            for doc in self.docs
            if doc["_id"] in ids and (doc.get("expires_at") is None or doc["expires_at"] > now)
        ]

        class Cursor:
            async def __aiter__(self):
                for doc in docs:
                    yield doc

        return Cursor()


async def _events(monkeypatch, docs, ids, *, enabled=True, permissions=None):
    routes = _load_session_routes_module(monkeypatch)
    collection = _ApprovalCollection(docs)
    storage = mongodb.ApprovalStorage()
    storage._collection = collection
    monkeypatch.setattr(mongodb, "get_approval_storage", lambda: storage)
    sessions = []

    class Manager:
        async def get_session(self, session_id):
            sessions.append(session_id)
            return SimpleNamespace(user_id="user-1", metadata={})

    class Writer:
        async def read_session_events(self, *_args, **_kwargs):
            return [{"event_type": "approval_required", "data": {"id": aid}} for aid in ids]

    monkeypatch.setattr(routes, "SessionManager", Manager)
    monkeypatch.setattr(sys.modules["src.infra.session.dual_writer"], "get_dual_writer", Writer)
    response = await routes.get_session_events(
        "session-1",
        event_types=None,
        run_id=None,
        exclude_run_id=None,
        limit=None,
        trace_limit=None,
        include_active_user_message=False,
        include_approval_statuses=enabled,
        user=SimpleNamespace(
            sub="user-1", permissions=["chat:write"] if permissions is None else permissions
        ),
    )
    return response, collection.calls, sessions


@pytest.mark.parametrize("count", [1, 100, 201])
async def test_session_approval_prefetch_batches_only_page_ids_without_session_n_plus_one(
    monkeypatch, count
):
    ids = [f"a-{index}" for index in range(count)]
    docs = [
        {
            "_id": aid,
            "id": aid,
            "message": "confirm",
            "user_id": "user-1",
            "metadata": {"approval_type": "scheduled_task_create"},
            "fields": [{"name": "answer"}],
        }
        for aid in ids
    ]
    response, calls, sessions = await _events(monkeypatch, docs, ids + ids[:1])
    assert len(calls) == (count + 99) // 100
    assert sessions == ["session-1"]
    assert len(response["events"]) == count + 1
    assert set(response["approval_statuses"]) == set(ids)
    assert response["approval_statuses"][ids[0]]["metadata"] == {
        "approval_type": "scheduled_task_create"
    }
    assert response["approval_statuses"][ids[0]]["fields"] == [{"name": "answer"}]
    assert all(projection == {"response": 0} for _query, projection in calls)
    assert all(len(query["_id"]["$in"]) <= 100 for query, _projection in calls)


async def test_session_approval_prefetch_filters_owners_missing_and_expired_records(monkeypatch):
    from datetime import timedelta

    from src.infra.utils.datetime import utc_now

    docs = [
        {
            "_id": "mine",
            "id": "mine",
            "message": "mine",
            "user_id": "user-1",
            "session_id": "other",
        },
        {"_id": "legacy", "id": "legacy", "message": "legacy", "session_id": "session-1"},
        {
            "_id": "foreign",
            "id": "foreign",
            "message": "secret",
            "user_id": "user-2",
            "session_id": "session-1",
        },
        {
            "_id": "foreign-legacy",
            "id": "foreign-legacy",
            "message": "secret",
            "session_id": "other",
        },
        {"_id": "orphan", "id": "orphan", "message": "secret"},
        {
            "_id": "expired",
            "id": "expired",
            "message": "secret",
            "user_id": "user-1",
            "expires_at": utc_now() - timedelta(seconds=1),
        },
    ]
    ids = [doc["_id"] for doc in docs] + ["missing"]
    response, _calls, sessions = await _events(monkeypatch, docs, ids)
    assert response["approval_statuses"]["mine"]["message"] == "mine"
    assert response["approval_statuses"]["legacy"]["message"] == "legacy"
    for aid in ids[2:]:
        assert response["approval_statuses"][aid] == {"id": aid, "status": "not_found"}
    assert sessions == ["session-1"]


@pytest.mark.parametrize("enabled,permissions", [(False, ["chat:write"]), (True, [])])
async def test_session_approval_prefetch_preserves_default_contract_and_write_permission(
    monkeypatch, enabled, permissions
):
    response, calls, _sessions = await _events(
        monkeypatch, [], ["missing"], enabled=enabled, permissions=permissions
    )
    assert "approval_statuses" not in response
    assert calls == []


async def test_session_approval_prefetch_failure_keeps_events_and_omits_optional_map(monkeypatch):
    def unavailable(self, query, projection):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(_ApprovalCollection, "find", unavailable)
    response, _calls, sessions = await _events(monkeypatch, [], ["fallback"])
    assert response["events"] == [{"event_type": "approval_required", "data": {"id": "fallback"}}]
    assert "approval_statuses" not in response
    assert sessions == ["session-1"]
