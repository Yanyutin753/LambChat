from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from src.plugins.workflow.storage import WorkflowPluginStorage


def _run_doc(
    run_id: str,
    *,
    status: str,
    mode: str,
    owner_user_id: str = "user-1",
    started_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "workflow_id": "wf-created",
        "version_id": "wfv-created",
        "owner_user_id": owner_user_id,
        "status": status,
        "mode": mode,
        "input": {"name": "LambChat"},
        "output": {},
        "error": None,
        "pause": {},
        "started_at": started_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        "finished_at": None,
    }


def _workflow_doc(
    workflow_id: str,
    *,
    name: str,
    status: str,
    owner_user_id: str = "user-1",
    description: str = "",
    updated_at: datetime | None = None,
) -> dict[str, Any]:
    now = updated_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        "workflow_id": workflow_id,
        "owner_user_id": owner_user_id,
        "name": name,
        "description": description,
        "status": status,
        "latest_version_id": f"{workflow_id}-latest",
        "published_version_id": f"{workflow_id}-published" if status == "published" else None,
        "version_count": 1,
        "created_at": now,
        "updated_at": now,
    }


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)
        self.sort_calls: list[tuple[Any, ...]] = []
        self.skip_calls: list[int] = []
        self.limit_calls: list[int] = []
        self._index = 0

    def sort(self, *args: Any) -> "_AsyncCursor":
        self.sort_calls.append(args)
        if args == ("started_at", 1):
            self._docs.sort(key=lambda doc: doc["started_at"])
        elif args == ("started_at", -1):
            self._docs.sort(key=lambda doc: doc["started_at"], reverse=True)
        elif args == ("updated_at", -1):
            self._docs.sort(key=lambda doc: doc["updated_at"], reverse=True)
        return self

    def skip(self, skip: int) -> "_AsyncCursor":
        self.skip_calls.append(skip)
        self._docs = self._docs[skip:]
        return self

    def limit(self, limit: int) -> "_AsyncCursor":
        self.limit_calls.append(limit)
        self._docs = self._docs[:limit]
        return self

    def __aiter__(self) -> "_AsyncCursor":
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._index >= len(self._docs):
            raise StopAsyncIteration
        doc = self._docs[self._index]
        self._index += 1
        return dict(doc)


class _FakeRunsCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = {doc["run_id"]: dict(doc) for doc in docs}
        self.find_queries: list[dict[str, Any]] = []
        self.update_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.last_cursor: _AsyncCursor | None = None

    def find(self, query: dict[str, Any]) -> _AsyncCursor:
        self.find_queries.append(query)
        docs = [
            doc
            for doc in self.docs.values()
            if all(self._matches_query_value(self._field_value(doc, key), value) for key, value in query.items())
        ]
        cursor = _AsyncCursor(docs)
        self.last_cursor = cursor
        return cursor

    def _matches_query_value(self, actual: Any, expected: Any) -> bool:
        if isinstance(expected, dict) and "$in" in expected:
            allowed = expected.get("$in")
            if not (isinstance(allowed, list) and actual in allowed):
                return False
        if isinstance(expected, dict) and "$lt" in expected:
            return actual is not None and actual < expected.get("$lt")
        if isinstance(expected, dict):
            return True
        return actual == expected

    def _field_value(self, doc: dict[str, Any], key: str) -> Any:
        value: Any = doc
        for part in key.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> SimpleNamespace:
        self.update_calls.append((query, update))
        doc = self.docs.get(str(query.get("run_id")))
        matched = bool(
            doc and all(self._matches_query_value(self._field_value(doc, key), value) for key, value in query.items())
        )
        if matched and doc:
            doc.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1 if matched else 0)

    async def delete_many(self, query: dict[str, Any]) -> SimpleNamespace:
        self.delete_calls.append(query)
        matched_ids = [
            run_id
            for run_id, doc in self.docs.items()
            if all(self._matches_query_value(self._field_value(doc, key), value) for key, value in query.items())
        ]
        for run_id in matched_ids:
            self.docs.pop(run_id, None)
        return SimpleNamespace(deleted_count=len(matched_ids))

    async def find_one(self, query: dict[str, Any], **_: Any) -> dict[str, Any] | None:
        doc = self.docs.get(str(query.get("run_id")))
        if doc and doc.get("owner_user_id") == query.get("owner_user_id"):
            return dict(doc)
        return None


class _FakeDefinitionsCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = [dict(doc) for doc in docs]
        self.count_queries: list[dict[str, Any]] = []
        self.find_queries: list[dict[str, Any]] = []
        self.last_cursor: _AsyncCursor | None = None

    async def count_documents(self, query: dict[str, Any]) -> int:
        self.count_queries.append(query)
        return len([doc for doc in self.docs if self._matches_query(doc, query)])

    def find(self, query: dict[str, Any]) -> _AsyncCursor:
        self.find_queries.append(query)
        cursor = _AsyncCursor([doc for doc in self.docs if self._matches_query(doc, query)])
        self.last_cursor = cursor
        return cursor

    def _matches_query(self, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, expected in query.items():
            if key == "$or":
                if not any(self._matches_query(doc, option) for option in expected):
                    return False
                continue
            if not self._matches_query_value(self._field_value(doc, key), expected):
                return False
        return True

    def _matches_query_value(self, actual: Any, expected: Any) -> bool:
        if isinstance(expected, dict) and "$ne" in expected:
            return actual != expected["$ne"]
        if isinstance(expected, dict) and "$regex" in expected:
            import re

            flags = re.IGNORECASE if "i" in str(expected.get("$options", "")) else 0
            return re.search(str(expected["$regex"]), str(actual or ""), flags) is not None
        if isinstance(expected, dict):
            return True
        return actual == expected

    def _field_value(self, doc: dict[str, Any], key: str) -> Any:
        value: Any = doc
        for part in key.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value


class _FakeEventsCollection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = list(docs or [])
        self.inserted_batches: list[list[dict[str, Any]]] = []
        self.delete_calls: list[dict[str, Any]] = []

    async def find_one(
        self,
        query: dict[str, Any],
        sort: list[tuple[str, int]] | None = None,
    ) -> dict[str, Any] | None:
        matches = [
            doc
            for doc in self.docs
            if doc.get("run_id") == query.get("run_id")
            and doc.get("owner_user_id") == query.get("owner_user_id")
        ]
        if not matches:
            return None
        reverse = bool(sort and sort[0] == ("sequence", -1))
        return dict(sorted(matches, key=lambda doc: doc.get("sequence", 0), reverse=reverse)[0])

    async def insert_many(self, docs: list[dict[str, Any]]) -> None:
        batch = [dict(doc) for doc in docs]
        self.inserted_batches.append(batch)
        self.docs.extend(batch)

    async def delete_many(self, query: dict[str, Any]) -> SimpleNamespace:
        self.delete_calls.append(query)
        run_filter = query.get("run_id")
        if isinstance(run_filter, dict) and isinstance(run_filter.get("$in"), list):
            allowed = set(run_filter["$in"])
            before = len(self.docs)
            self.docs = [doc for doc in self.docs if doc.get("run_id") not in allowed]
            return SimpleNamespace(deleted_count=before - len(self.docs))
        return SimpleNamespace(deleted_count=0)


@pytest.mark.asyncio
async def test_list_workflows_filters_owner_status_and_query_before_pagination() -> None:
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    definitions = _FakeDefinitionsCollection(
        [
            _workflow_doc("wf-draft", name="Draft Intake", status="draft", updated_at=started),
            _workflow_doc(
                "wf-billing",
                name="Billing Review",
                status="published",
                description="Invoice approval flow",
                updated_at=started.replace(hour=2),
            ),
            _workflow_doc(
                "wf-archived",
                name="Archived Billing",
                status="archived",
                description="Old invoice flow",
                updated_at=started.replace(hour=3),
            ),
            _workflow_doc(
                "wf-other",
                name="Billing Review",
                status="published",
                owner_user_id="user-2",
                updated_at=started.replace(hour=4),
            ),
        ]
    )
    storage = WorkflowPluginStorage()
    storage._definitions = definitions  # type: ignore[assignment]

    default_result = await storage.list_workflows(owner_user_id="user-1")
    filtered_result = await storage.list_workflows(
        owner_user_id="user-1",
        query="invoice",
        status_filter="published",
        skip=0,
        limit=10,
    )

    assert [workflow.workflow_id for workflow in default_result.workflows] == [
        "wf-billing",
        "wf-draft",
    ]
    assert default_result.total == 2
    assert [workflow.workflow_id for workflow in filtered_result.workflows] == ["wf-billing"]
    assert filtered_result.total == 1
    assert definitions.count_queries[0] == {
        "owner_user_id": "user-1",
        "status": {"$ne": "archived"},
    }
    assert definitions.count_queries[1]["owner_user_id"] == "user-1"
    assert definitions.count_queries[1]["status"] == "published"
    assert definitions.count_queries[1]["$or"][0]["workflow_id"]["$options"] == "i"
    assert definitions.find_queries == definitions.count_queries
    assert definitions.last_cursor is not None
    assert definitions.last_cursor.sort_calls[-1] == ("updated_at", -1)
    assert definitions.last_cursor.skip_calls[-1] == 0
    assert definitions.last_cursor.limit_calls[-1] == 10


@pytest.mark.asyncio
async def test_fail_stale_running_runs_marks_only_durable_running_runs_failed() -> None:
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    runs = _FakeRunsCollection(
        [
            _run_doc("wfr-newer", status="running", mode="async", started_at=started.replace(hour=1)),
            _run_doc("wfr-stream", status="running", mode="stream", started_at=started.replace(hour=2)),
            _run_doc("wfr-sync", status="running", mode="sync"),
            _run_doc("wfr-done", status="succeeded", mode="async"),
            _run_doc("wfr-older", status="running", mode="async", started_at=started),
        ]
    )
    events = _FakeEventsCollection(
        [
            {
                "event_id": "existing",
                "run_id": "wfr-newer",
                "workflow_id": "wf-created",
                "version_id": "wfv-created",
                "owner_user_id": "user-1",
                "sequence": 2,
                "event_type": "run_queued",
                "payload": {},
                "created_at": started,
            }
        ]
    )
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]
    storage._events = events  # type: ignore[assignment]

    recovered = await storage.fail_stale_running_runs(error="server_restart", limit=10)

    assert recovered == 3
    assert runs.find_queries == [{"status": "running", "mode": {"$in": ["async", "stream"]}}]
    assert runs.last_cursor is not None
    assert runs.last_cursor.sort_calls == [("started_at", 1)]
    assert runs.last_cursor.limit_calls == [10]
    assert {call[0]["run_id"] for call in runs.update_calls} == {
        "wfr-older",
        "wfr-newer",
        "wfr-stream",
    }
    assert runs.docs["wfr-older"]["status"] == "failed"
    assert runs.docs["wfr-newer"]["status"] == "failed"
    assert runs.docs["wfr-stream"]["status"] == "failed"
    assert runs.docs["wfr-sync"]["status"] == "running"
    assert runs.docs["wfr-done"]["status"] == "succeeded"
    inserted = [event for batch in events.inserted_batches for event in batch]
    assert [event["run_id"] for event in inserted] == ["wfr-older", "wfr-newer", "wfr-stream"]
    assert [event["sequence"] for event in inserted] == [1, 3, 1]
    assert all(event["event_type"] == "run_failed" for event in inserted)
    assert all(event["payload"] == {"error": "server_restart", "recoverable": True} for event in inserted)


@pytest.mark.asyncio
async def test_cancel_run_marks_running_run_cancelled_with_event() -> None:
    runs = _FakeRunsCollection([_run_doc("wfr-running", status="running", mode="async")])
    events = _FakeEventsCollection()
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]
    storage._events = events  # type: ignore[assignment]

    run, persisted_events = await storage.cancel_run(
        run_id="wfr-running",
        owner_user_id="user-1",
    )

    assert run.status == "cancelled"
    assert run.error == "workflow_run_cancelled_by_user"
    assert persisted_events[0].event_type == "run_cancelled"
    assert persisted_events[0].payload == {
        "error": "workflow_run_cancelled_by_user",
        "cancelled_by": "user-1",
    }
    assert runs.docs["wfr-running"]["status"] == "cancelled"
    assert runs.docs["wfr-running"]["finished_at"] is not None


@pytest.mark.asyncio
async def test_append_run_events_truncates_oversized_payload_before_insert() -> None:
    run_doc = _run_doc("wfr-running", status="running", mode="async")
    runs = _FakeRunsCollection([run_doc])
    events = _FakeEventsCollection()
    storage = WorkflowPluginStorage(max_event_payload_bytes=1024)
    storage._runs = runs  # type: ignore[assignment]
    storage._events = events  # type: ignore[assignment]

    persisted_events = await storage.append_run_events(
        run=storage._run_from_doc(run_doc),
        events=[
            {"event_type": "node_finished", "payload": {"answer": "ok"}},
            {
                "event_type": "node_finished",
                "payload": {"answer": "x" * 2048, "metadata": {"source": "large"}},
            },
        ],
    )

    inserted = events.inserted_batches[0]
    assert inserted[0]["payload"] == {"answer": "ok"}
    assert inserted[1]["payload"]["truncated"] is True
    assert inserted[1]["payload"]["reason"] == "workflow_event_payload_too_large"
    assert inserted[1]["payload"]["original_bytes"] > inserted[1]["payload"]["max_bytes"]
    assert inserted[1]["payload"]["max_bytes"] == 1024
    assert inserted[1]["payload"]["keys"] == ["answer", "metadata"]
    assert "x" * 64 not in repr(inserted[1]["payload"])
    assert persisted_events[1].payload == inserted[1]["payload"]


@pytest.mark.asyncio
async def test_cancel_run_does_not_append_event_when_concurrent_terminal_update_wins() -> None:
    class _RacingRunsCollection(_FakeRunsCollection):
        async def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> SimpleNamespace:
            doc = self.docs["wfr-running"]
            doc["status"] = "succeeded"
            doc["output"] = {"answer": "already done"}
            doc["finished_at"] = datetime(2026, 1, 2, tzinfo=timezone.utc)
            return await super().update_one(query, update)

    runs = _RacingRunsCollection([_run_doc("wfr-running", status="running", mode="async")])
    events = _FakeEventsCollection()
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]
    storage._events = events  # type: ignore[assignment]

    with pytest.raises(ValueError, match="workflow_run_not_cancellable:succeeded"):
        await storage.cancel_run(run_id="wfr-running", owner_user_id="user-1")

    assert runs.docs["wfr-running"]["status"] == "succeeded"
    assert runs.docs["wfr-running"]["output"] == {"answer": "already done"}
    assert events.inserted_batches == []


@pytest.mark.asyncio
async def test_cancel_run_does_not_append_duplicate_event_when_concurrent_cancel_wins() -> None:
    class _RacingRunsCollection(_FakeRunsCollection):
        async def update_one(self, query: dict[str, Any], update: dict[str, Any]) -> SimpleNamespace:
            doc = self.docs["wfr-running"]
            doc["status"] = "cancelled"
            doc["error"] = "workflow_run_cancelled_by_user"
            doc["finished_at"] = datetime(2026, 1, 2, tzinfo=timezone.utc)
            return await super().update_one(query, update)

    runs = _RacingRunsCollection([_run_doc("wfr-running", status="running", mode="async")])
    events = _FakeEventsCollection()
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]
    storage._events = events  # type: ignore[assignment]

    with pytest.raises(ValueError, match="workflow_run_not_cancellable:cancelled"):
        await storage.cancel_run(run_id="wfr-running", owner_user_id="user-1")

    assert runs.docs["wfr-running"]["status"] == "cancelled"
    assert events.inserted_batches == []


@pytest.mark.asyncio
async def test_finish_run_does_not_overwrite_terminal_run() -> None:
    terminal = _run_doc("wfr-cancelled", status="cancelled", mode="async")
    terminal["error"] = "workflow_run_cancelled_by_user"
    runs = _FakeRunsCollection([terminal])
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]

    run = await storage.finish_run(
        run_id="wfr-cancelled",
        owner_user_id="user-1",
        status="succeeded",
        output={"answer": "late"},
    )

    assert run.status == "cancelled"
    assert run.error == "workflow_run_cancelled_by_user"
    assert run.output == {}
    assert runs.update_calls[0][0] == {
        "run_id": "wfr-cancelled",
        "owner_user_id": "user-1",
        "status": {"$in": ["queued", "running", "paused"]},
    }
    assert runs.docs["wfr-cancelled"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_finish_run_allows_paused_run_to_resume_to_terminal_status() -> None:
    runs = _FakeRunsCollection([_run_doc("wfr-paused", status="paused", mode="async")])
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]

    run = await storage.finish_run(
        run_id="wfr-paused",
        owner_user_id="user-1",
        status="succeeded",
        output={"answer": "approved"},
    )

    assert run.status == "succeeded"
    assert run.output == {"answer": "approved"}
    assert runs.docs["wfr-paused"]["finished_at"] is not None


@pytest.mark.asyncio
async def test_pause_run_marks_run_paused_with_resume_state() -> None:
    runs = _FakeRunsCollection([_run_doc("wfr-running", status="running", mode="sync")])
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]

    run = await storage.pause_run(
        run_id="wfr-running",
        owner_user_id="user-1",
        output={"name": "LambChat"},
        error="workflow_human_approval_paused:approval",
        pause={"kind": "human_approval", "resume_state": {"node_id": "approval"}},
    )

    assert run.status == "paused"
    assert run.finished_at is None
    assert run.output == {"name": "LambChat"}
    assert run.pause["resume_state"] == {"node_id": "approval"}
    assert runs.docs["wfr-running"]["status"] == "paused"


@pytest.mark.asyncio
async def test_pause_run_does_not_overwrite_terminal_run() -> None:
    terminal = _run_doc("wfr-cancelled", status="cancelled", mode="async")
    terminal["error"] = "workflow_run_cancelled_by_user"
    runs = _FakeRunsCollection([terminal])
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]

    run = await storage.pause_run(
        run_id="wfr-cancelled",
        owner_user_id="user-1",
        output={"name": "late"},
        error="workflow_human_approval_paused:approval",
        pause={"kind": "human_approval", "resume_state": {"node_id": "approval"}},
    )

    assert run.status == "cancelled"
    assert run.error == "workflow_run_cancelled_by_user"
    assert run.output == {}
    assert runs.update_calls[0][0] == {
        "run_id": "wfr-cancelled",
        "owner_user_id": "user-1",
        "status": {"$in": ["queued", "running", "paused"]},
    }
    assert runs.docs["wfr-cancelled"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_list_pending_approval_runs_filters_owner_and_human_approval_pause() -> None:
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    pending_newer = _run_doc(
        "wfr-newer",
        status="paused",
        mode="async",
        started_at=started.replace(hour=2),
    )
    pending_newer["pause"] = {"kind": "human_approval", "pending_approval": {"node_id": "approval-2"}}
    pending_older = _run_doc(
        "wfr-older",
        status="paused",
        mode="async",
        started_at=started,
    )
    pending_older["pause"] = {"kind": "human_approval", "pending_approval": {"node_id": "approval-1"}}
    other_owner = _run_doc("wfr-other-owner", status="paused", mode="async", owner_user_id="user-2")
    other_owner["pause"] = {"kind": "human_approval"}
    waiting_other_pause = _run_doc("wfr-tool", status="paused", mode="async")
    waiting_other_pause["pause"] = {"kind": "tool_wait"}
    succeeded = _run_doc("wfr-done", status="succeeded", mode="async")
    succeeded["pause"] = {"kind": "human_approval"}
    runs = _FakeRunsCollection([pending_older, pending_newer, other_owner, waiting_other_pause, succeeded])
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]

    result = await storage.list_pending_approval_runs(owner_user_id="user-1", skip=1, limit=1)

    assert [run.run_id for run in result] == ["wfr-older"]
    assert runs.find_queries == [
        {
            "owner_user_id": "user-1",
            "status": "paused",
            "pause.kind": "human_approval",
        }
    ]
    assert runs.last_cursor is not None
    assert runs.last_cursor.sort_calls == [("started_at", -1)]
    assert runs.last_cursor.skip_calls == [1]
    assert runs.last_cursor.limit_calls == [1]


@pytest.mark.asyncio
async def test_cancel_run_accepts_paused_run() -> None:
    runs = _FakeRunsCollection([_run_doc("wfr-paused", status="paused", mode="sync")])
    events = _FakeEventsCollection()
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]
    storage._events = events  # type: ignore[assignment]

    run, persisted_events = await storage.cancel_run(
        run_id="wfr-paused",
        owner_user_id="user-1",
    )

    assert run.status == "cancelled"
    assert persisted_events[0].event_type == "run_cancelled"


@pytest.mark.asyncio
async def test_cancel_run_rejects_terminal_run() -> None:
    runs = _FakeRunsCollection([_run_doc("wfr-done", status="succeeded", mode="async")])
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]
    storage._events = _FakeEventsCollection()  # type: ignore[assignment]

    with pytest.raises(ValueError, match="workflow_run_not_cancellable:succeeded"):
        await storage.cancel_run(run_id="wfr-done", owner_user_id="user-1")


@pytest.mark.asyncio
async def test_delete_terminal_run_logs_before_removes_terminal_runs_and_events() -> None:
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    new = datetime(2026, 2, 1, tzinfo=timezone.utc)
    old_done = _run_doc("wfr-old-done", status="succeeded", mode="sync", started_at=old)
    old_done["finished_at"] = old
    old_failed = _run_doc("wfr-old-failed", status="failed", mode="async", started_at=old)
    old_failed["finished_at"] = old
    old_cancelled = _run_doc("wfr-old-cancelled", status="cancelled", mode="stream", started_at=old)
    old_cancelled["finished_at"] = old
    old_paused = _run_doc("wfr-old-paused", status="paused", mode="async", started_at=old)
    old_paused["finished_at"] = old
    new_done = _run_doc("wfr-new-done", status="succeeded", mode="sync", started_at=new)
    new_done["finished_at"] = new
    runs = _FakeRunsCollection([old_done, old_failed, old_cancelled, old_paused, new_done])
    events = _FakeEventsCollection(
        [
            {"run_id": "wfr-old-done", "owner_user_id": "user-1"},
            {"run_id": "wfr-old-failed", "owner_user_id": "user-1"},
            {"run_id": "wfr-old-cancelled", "owner_user_id": "user-1"},
            {"run_id": "wfr-old-paused", "owner_user_id": "user-1"},
            {"run_id": "wfr-new-done", "owner_user_id": "user-1"},
        ]
    )
    storage = WorkflowPluginStorage()
    storage._runs = runs  # type: ignore[assignment]
    storage._events = events  # type: ignore[assignment]

    deleted = await storage.delete_terminal_run_logs_before(datetime(2026, 1, 15, tzinfo=timezone.utc))

    assert deleted == 3
    assert set(runs.docs) == {"wfr-old-paused", "wfr-new-done"}
    assert [event["run_id"] for event in events.docs] == ["wfr-old-paused", "wfr-new-done"]
    assert events.delete_calls == [
        {"run_id": {"$in": ["wfr-old-done", "wfr-old-failed", "wfr-old-cancelled"]}}
    ]
    assert runs.delete_calls == [
        {
            "status": {"$in": ["succeeded", "failed", "cancelled"]},
            "finished_at": {"$lt": datetime(2026, 1, 15, tzinfo=timezone.utc)},
        }
    ]
