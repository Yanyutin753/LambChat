import asyncio
from types import SimpleNamespace

import pytest

from src.infra.session.manager import SessionManager
from src.kernel.schemas.session import Session


def test_build_fork_session_name_reuses_source_title() -> None:
    assert SessionManager._build_fork_session_name("Budget planning") == "Budget planning (Fork)"


def test_build_fork_session_name_falls_back_for_blank_title() -> None:
    assert SessionManager._build_fork_session_name("  ") == "New Chat (Fork)"


def test_build_fork_session_name_does_not_stack_fork_suffix() -> None:
    assert (
        SessionManager._build_fork_session_name("Budget planning (Fork)")
        == "Budget planning (Fork)"
    )


class _AsyncTraceCursor:
    def __init__(self, traces):
        self._traces = traces
        self.to_list_called = False

    def sort(self, *_args):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._traces:
            raise StopAsyncIteration
        return self._traces.pop(0)

    async def to_list(self, length=None):
        self.to_list_called = True
        return list(self._traces)


class _FakeTraceCollection:
    def __init__(self, traces):
        self.cursor = _AsyncTraceCursor(list(traces))
        self.inserted_docs = None
        self.insert_many_calls = []
        self.find_calls = []

    def find(self, *_args, **_kwargs):
        self.find_calls.append((_args, _kwargs))
        return self.cursor

    async def insert_many(self, docs):
        self.inserted_docs = docs
        self.insert_many_calls.append(list(docs))


class _FakeSessionStorage:
    def __init__(self, *, allow_trace_write=True, validate_trace_write=True):
        self.deleted_session_ids = []
        self.rebuilt_session_ids = []
        self.allow_trace_write = allow_trace_write
        self.validate_trace_write_result = validate_trace_write
        self.acquired_trace_writes = []
        self.released_trace_writes = []

    async def acquire_trace_write(self, session_id):
        self.acquired_trace_writes.append(session_id)
        return f"lease:{session_id}" if self.allow_trace_write else None

    async def release_trace_write(self, session_id, lease_id):
        self.released_trace_writes.append((session_id, lease_id))

    async def validate_trace_write(self, session_id, lease_id):
        del session_id, lease_id
        return self.validate_trace_write_result

    async def create(self, session_data, user_id=None):
        return Session(
            id="target", user_id=user_id, name=session_data.name, metadata=session_data.metadata
        )

    async def delete(self, session_id):
        self.deleted_session_ids.append(session_id)
        return True

    async def rebuild_search_index(self, session_id):
        self.rebuilt_session_ids.append(session_id)
        return True


@pytest.mark.asyncio
async def test_clone_history_streams_traces_until_target_run() -> None:
    traces = [
        {"run_id": "run-1", "events": [], "started_at": 1},
        {"run_id": "run-2", "events": [], "started_at": 2},
        {"run_id": "run-3", "events": [], "started_at": 3},
    ]
    collection = _FakeTraceCollection(traces)
    manager = SessionManager()
    storage = _FakeSessionStorage()
    manager.storage = storage
    manager._trace_storage = SimpleNamespace(collection=collection)

    cloned_docs = await manager._clone_history_to_session(
        source_session=Session(id="source", user_id="user"),
        target_session=Session(id="target", user_id="user"),
        target={
            "run_id": "run-2",
            "target_type": "assistant",
            "completed_run_ids": ["run-1", "run-2"],
        },
        user_id="user",
    )

    assert len(cloned_docs) == 2
    assert collection.cursor.to_list_called is False
    assert collection.inserted_docs is not None
    assert [doc["run_id"] for doc in collection.inserted_docs] == ["run-1", "run-2"]
    assert storage.released_trace_writes == [("target", "lease:target")]


@pytest.mark.asyncio
async def test_clone_history_discards_exact_late_inserts_after_lease_loss() -> None:
    traces = [{"run_id": "run-1", "events": [], "started_at": 1}]

    class _BlockingTraceCollection(_FakeTraceCollection):
        def __init__(self) -> None:
            super().__init__(traces)
            self.insert_started = asyncio.Event()
            self.allow_insert = asyncio.Event()

        async def insert_many(self, docs):
            self.insert_started.set()
            await self.allow_insert.wait()
            await super().insert_many(docs)

    collection = _BlockingTraceCollection()

    class _TraceStorage:
        def __init__(self) -> None:
            self.collection = collection
            self.discarded: list[tuple[str, str, list[str]]] = []

        async def discard_session_trace_writes_after_lease_loss(
            self,
            session_id: str,
            lease_id: str,
            trace_ids: list[str],
        ) -> bool:
            self.discarded.append((session_id, lease_id, trace_ids))
            return True

    manager = SessionManager()
    storage = _FakeSessionStorage(validate_trace_write=True)
    trace_storage = _TraceStorage()
    manager.storage = storage
    manager._trace_storage = trace_storage

    clone = asyncio.create_task(
        manager._clone_history_to_session(
            source_session=Session(id="source", user_id="user"),
            target_session=Session(id="target", user_id="user"),
            target={
                "run_id": "run-1",
                "target_type": "assistant",
                "completed_run_ids": ["run-1"],
            },
            user_id="user",
        )
    )
    await collection.insert_started.wait()
    storage.validate_trace_write_result = False
    collection.allow_insert.set()

    with pytest.raises(Exception, match="session_trace_write_lease_lost"):
        await clone

    assert len(trace_storage.discarded) == 1
    session_id, lease_id, trace_ids = trace_storage.discarded[0]
    assert (session_id, lease_id) == ("target", "lease:target")
    assert trace_ids == [collection.inserted_docs[0]["trace_id"]]
    assert storage.released_trace_writes == [("target", "lease:target")]


@pytest.mark.asyncio
async def test_clone_history_shields_final_lease_check_and_discards_exact_inserts() -> None:
    traces = [{"run_id": "run-1", "events": [], "started_at": 1}]
    collection = _FakeTraceCollection(traces)

    class _BlockingValidationStorage(_FakeSessionStorage):
        def __init__(self) -> None:
            super().__init__(validate_trace_write=False)
            self.validation_started = asyncio.Event()
            self.allow_validation = asyncio.Event()

        async def validate_trace_write(self, session_id, lease_id):
            del session_id, lease_id
            self.validation_started.set()
            await self.allow_validation.wait()
            return False

    class _TraceStorage:
        def __init__(self) -> None:
            self.collection = collection
            self.discarded: list[tuple[str, str, list[str]]] = []

        async def discard_session_trace_writes_after_lease_loss(
            self,
            session_id: str,
            lease_id: str,
            trace_ids: list[str],
        ) -> bool:
            self.discarded.append((session_id, lease_id, trace_ids))
            return True

    manager = SessionManager()
    storage = _BlockingValidationStorage()
    trace_storage = _TraceStorage()
    manager.storage = storage
    manager._trace_storage = trace_storage

    clone = asyncio.create_task(
        manager._clone_history_to_session(
            source_session=Session(id="source", user_id="user"),
            target_session=Session(id="target", user_id="user"),
            target={
                "run_id": "run-1",
                "target_type": "assistant",
                "completed_run_ids": ["run-1"],
            },
            user_id="user",
        )
    )
    await storage.validation_started.wait()
    clone.cancel()
    storage.allow_validation.set()

    with pytest.raises(Exception, match="session_trace_write_lease_lost"):
        await clone

    inserted_trace_id = collection.inserted_docs[0]["trace_id"]
    assert trace_storage.discarded == [("target", "lease:target", [inserted_trace_id])]
    assert storage.released_trace_writes == [("target", "lease:target")]


@pytest.mark.asyncio
async def test_clone_history_shields_compensation_after_final_lease_check_fails() -> None:
    traces = [{"run_id": "run-1", "events": [], "started_at": 1}]
    collection = _FakeTraceCollection(traces)

    class _TraceStorage:
        def __init__(self) -> None:
            self.collection = collection
            self.discard_started = asyncio.Event()
            self.allow_discard = asyncio.Event()
            self.discarded: list[tuple[str, str, list[str]]] = []

        async def discard_session_trace_writes_after_lease_loss(
            self,
            session_id: str,
            lease_id: str,
            trace_ids: list[str],
        ) -> bool:
            self.discard_started.set()
            await self.allow_discard.wait()
            self.discarded.append((session_id, lease_id, trace_ids))
            return True

    manager = SessionManager()
    storage = _FakeSessionStorage(validate_trace_write=False)
    trace_storage = _TraceStorage()
    manager.storage = storage
    manager._trace_storage = trace_storage

    clone = asyncio.create_task(
        manager._clone_history_to_session(
            source_session=Session(id="source", user_id="user"),
            target_session=Session(id="target", user_id="user"),
            target={
                "run_id": "run-1",
                "target_type": "assistant",
                "completed_run_ids": ["run-1"],
            },
            user_id="user",
        )
    )
    await trace_storage.discard_started.wait()
    clone.cancel()
    trace_storage.allow_discard.set()

    with pytest.raises(Exception, match="session_trace_write_lease_lost"):
        await clone

    inserted_trace_id = collection.inserted_docs[0]["trace_id"]
    assert trace_storage.discarded == [("target", "lease:target", [inserted_trace_id])]
    assert storage.released_trace_writes == [("target", "lease:target")]


@pytest.mark.asyncio
async def test_clone_history_survives_repeated_cancellation_until_child_is_compensated() -> None:
    traces = [{"run_id": "run-1", "events": [], "started_at": 1}]

    class _BlockingTraceCollection(_FakeTraceCollection):
        def __init__(self) -> None:
            super().__init__(traces)
            self.insert_started = asyncio.Event()
            self.allow_insert = asyncio.Event()
            self.insert_completed = False
            self.insert_cancelled = False

        async def insert_many(self, docs):
            self.insert_started.set()
            try:
                await self.allow_insert.wait()
            except asyncio.CancelledError:
                self.insert_cancelled = True
                raise
            await super().insert_many(docs)
            self.insert_completed = True

    class _RepeatedCancellationStorage(_FakeSessionStorage):
        def __init__(self) -> None:
            super().__init__(validate_trace_write=False)
            self.owner: asyncio.Task[None] | None = None
            self.second_cancel_turn_completed = asyncio.Event()
            self.second_cancel_scheduled = False

        async def acquire_trace_write(self, session_id):
            self.owner = asyncio.current_task()
            return await super().acquire_trace_write(session_id)

        async def validate_trace_write(self, session_id, lease_id):
            del session_id, lease_id
            if not self.second_cancel_scheduled:
                self.second_cancel_scheduled = True
                loop = asyncio.get_running_loop()

                def _cancel_owner_again() -> None:
                    assert self.owner is not None
                    self.owner.cancel()
                    loop.call_soon(self.second_cancel_turn_completed.set)

                loop.call_soon(_cancel_owner_again)
            return False

    collection = _BlockingTraceCollection()

    class _TraceStorage:
        def __init__(self) -> None:
            self.collection = collection
            self.discarded: list[tuple[str, str, list[str]]] = []

        async def discard_session_trace_writes_after_lease_loss(
            self,
            session_id: str,
            lease_id: str,
            trace_ids: list[str],
        ) -> bool:
            self.discarded.append((session_id, lease_id, trace_ids))
            return True

    manager = SessionManager()
    storage = _RepeatedCancellationStorage()
    trace_storage = _TraceStorage()
    manager.storage = storage
    manager._trace_storage = trace_storage

    clone = asyncio.create_task(
        manager._clone_history_to_session(
            source_session=Session(id="source", user_id="user"),
            target_session=Session(id="target", user_id="user"),
            target={
                "run_id": "run-1",
                "target_type": "assistant",
                "completed_run_ids": ["run-1"],
            },
            user_id="user",
        )
    )
    await collection.insert_started.wait()
    clone.cancel()
    await storage.second_cancel_turn_completed.wait()
    collection.allow_insert.set()

    with pytest.raises(Exception, match="session_trace_write_lease_lost"):
        await clone

    inserted_trace_id = collection.inserted_docs[0]["trace_id"]
    assert collection.insert_completed is True
    assert collection.insert_cancelled is False
    assert trace_storage.discarded == [("target", "lease:target", [inserted_trace_id])]
    assert storage.released_trace_writes == [("target", "lease:target")]


@pytest.mark.asyncio
async def test_clone_history_inserts_traces_in_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.infra.session.manager.SESSION_FORK_TRACE_INSERT_BATCH_SIZE",
        2,
        raising=False,
    )
    traces = [{"run_id": f"run-{index}", "events": [], "started_at": index} for index in range(5)]
    collection = _FakeTraceCollection(traces)
    manager = SessionManager()
    manager.storage = _FakeSessionStorage()
    manager._trace_storage = SimpleNamespace(collection=collection)

    result = await manager._clone_history_to_session(
        source_session=Session(id="source", user_id="user"),
        target_session=Session(id="target", user_id="user"),
        target={
            "run_id": "run-5",
            "target_type": "assistant",
            "completed_run_ids": [f"run-{index}" for index in range(5)],
        },
        user_id="user",
    )

    inserted_docs = [doc for call in collection.insert_many_calls for doc in call]
    assert result.copied_trace_count == 5
    assert [len(call) for call in collection.insert_many_calls] == [2, 2, 1]
    assert [doc["run_id"] for doc in inserted_docs] == [
        "run-0",
        "run-1",
        "run-2",
        "run-3",
        "run-4",
    ]


@pytest.mark.asyncio
async def test_clone_history_returns_count_without_retaining_cloned_trace_docs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.infra.session.manager.SESSION_FORK_TRACE_INSERT_BATCH_SIZE",
        2,
        raising=False,
    )
    traces = [
        {
            "run_id": f"run-{index}",
            "events": [
                {
                    "event_type": "user:message",
                    "data": {"content": f"hello {index}"},
                }
            ],
            "started_at": index,
        }
        for index in range(5)
    ]
    collection = _FakeTraceCollection(traces)
    manager = SessionManager()
    manager.storage = _FakeSessionStorage()
    manager._trace_storage = SimpleNamespace(collection=collection)

    result = await manager._clone_history_to_session(
        source_session=Session(id="source", user_id="user"),
        target_session=Session(id="target", user_id="user"),
        target={
            "run_id": "run-4",
            "target_type": "assistant",
        },
        user_id="user",
        collect_checkpoint_messages=True,
    )

    assert result.copied_trace_count == 5
    assert [len(call) for call in collection.insert_many_calls] == [2, 2, 1]
    assert [message.content for message in result.checkpoint_messages] == [
        "hello 0",
        "hello 1",
        "hello 2",
        "hello 3",
        "hello 4",
    ]
    assert not hasattr(result, "cloned_docs")


@pytest.mark.asyncio
async def test_clone_history_does_not_retain_compat_docs_for_completed_run_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "src.infra.session.manager.SESSION_FORK_TRACE_INSERT_BATCH_SIZE",
        2,
        raising=False,
    )
    traces = [
        {
            "run_id": f"run-{index}",
            "events": [{"event_type": "message:chunk", "data": {"content": "x" * 1000}}],
            "started_at": index,
        }
        for index in range(5)
    ]
    collection = _FakeTraceCollection(traces)
    manager = SessionManager()
    manager.storage = _FakeSessionStorage()
    manager._trace_storage = SimpleNamespace(collection=collection)

    result = await manager._clone_history_to_session(
        source_session=Session(id="source", user_id="user"),
        target_session=Session(id="target", user_id="user"),
        target={
            "run_id": "run-4",
            "target_type": "assistant",
            "completed_run_ids": [f"run-{index}" for index in range(5)],
        },
        user_id="user",
    )

    assert result.copied_trace_count == 5
    assert result._compat_docs == []  # type: ignore[attr-defined]
    assert [len(call) for call in collection.insert_many_calls] == [2, 2, 1]


@pytest.mark.asyncio
async def test_clone_history_offloads_trace_document_cloning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infra.session.manager as manager_module

    traces = [
        {"run_id": "run-1", "events": [{"data": {"content": "hello"}}], "started_at": 1},
        {"run_id": "run-2", "events": [{"data": {"content": "world"}}], "started_at": 2},
    ]
    collection = _FakeTraceCollection(traces)
    manager = SessionManager()
    manager.storage = _FakeSessionStorage()
    manager._trace_storage = SimpleNamespace(collection=collection)
    offloaded: list[str] = []

    async def fake_run_blocking_io(func, /, *args, **kwargs):
        offloaded.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(manager_module, "run_blocking_io", fake_run_blocking_io, raising=False)

    cloned_docs = await manager._clone_history_to_session(
        source_session=Session(id="source", user_id="user"),
        target_session=Session(id="target", user_id="user"),
        target={
            "run_id": "run-2",
            "target_type": "assistant",
            "completed_run_ids": ["run-1", "run-2"],
        },
        user_id="user",
    )

    assert len(cloned_docs) == 2
    assert offloaded == ["_build_cloned_trace_doc", "_build_cloned_trace_doc"]


@pytest.mark.asyncio
async def test_clone_history_offloads_checkpoint_message_rebuild(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infra.session.manager as manager_module

    traces = [
        {
            "run_id": "run-1",
            "events": [
                {
                    "event_type": "user:message",
                    "data": {"content": "hello"},
                },
                {
                    "event_type": "message:chunk",
                    "data": {"content": "hi"},
                },
            ],
            "started_at": 1,
        },
    ]
    collection = _FakeTraceCollection(traces)
    manager = SessionManager()
    manager.storage = _FakeSessionStorage()
    manager._trace_storage = SimpleNamespace(collection=collection)
    offloaded: list[str] = []

    async def fake_run_blocking_io(func, /, *args, **kwargs):
        offloaded.append(func.__name__)
        return func(*args, **kwargs)

    monkeypatch.setattr(manager_module, "run_blocking_io", fake_run_blocking_io, raising=False)

    result = await manager._clone_history_to_session(
        source_session=Session(id="source", user_id="user"),
        target_session=Session(id="target", user_id="user"),
        target={
            "run_id": "run-1",
            "target_type": "assistant",
        },
        user_id="user",
        collect_checkpoint_messages=True,
    )

    assert [message.content for message in result.checkpoint_messages] == ["hello", "hi"]
    assert "build_messages_from_trace_events" in offloaded


@pytest.mark.asyncio
async def test_resolve_fork_target_does_not_retain_all_prior_run_ids() -> None:
    traces = [{"run_id": f"run-{index}", "events": [], "started_at": index} for index in range(5)]
    traces.append(
        {
            "run_id": "run-target",
            "trace_id": "trace-target",
            "events": [
                {
                    "event_type": "user:message",
                    "data": {"message_id": "message-target"},
                }
            ],
            "started_at": 5,
        }
    )
    collection = _FakeTraceCollection(traces)
    manager = SessionManager()
    manager._trace_storage = SimpleNamespace(collection=collection)

    target = await manager._resolve_fork_target("source", "message-target")

    assert target["target_type"] == "user"
    assert target["run_id"] == "run-target"
    assert target["completed_run_count"] == 5
    assert "completed_run_ids" not in target
    assert collection.cursor.to_list_called is False


@pytest.mark.asyncio
async def test_resolve_fork_target_streams_traces_until_message() -> None:
    traces = [
        {"run_id": "run-1", "events": [], "started_at": 1},
        {
            "run_id": "run-2",
            "trace_id": "trace-2",
            "events": [
                {
                    "event_type": "user:message",
                    "data": {"message_id": "message-2"},
                }
            ],
            "started_at": 2,
        },
        {"run_id": "run-3", "events": [], "started_at": 3},
    ]
    collection = _FakeTraceCollection(traces)
    manager = SessionManager()
    manager._trace_storage = SimpleNamespace(collection=collection)

    target = await manager._resolve_fork_target("source", "message-2")

    assert target["target_type"] == "user"
    assert target["run_id"] == "run-2"
    assert target["completed_run_count"] == 1
    assert "completed_run_ids" not in target
    assert collection.cursor.to_list_called is False


@pytest.mark.asyncio
async def test_resolve_fork_target_projects_only_needed_trace_fields() -> None:
    traces = [
        {
            "run_id": "run-1",
            "trace_id": "trace-1",
            "events": [
                {
                    "event_type": "user:message",
                    "data": {"message_id": "message-1"},
                }
            ],
            "started_at": 1,
            "large_metadata": "x" * 100_000,
        },
    ]
    collection = _FakeTraceCollection(traces)
    manager = SessionManager()
    manager._trace_storage = SimpleNamespace(collection=collection)

    target = await manager._resolve_fork_target("source", "message-1")

    assert target["run_id"] == "run-1"
    assert collection.find_calls[0] == (
        (
            {"session_id": "source"},
            {
                "_id": 0,
                "trace_id": 1,
                "run_id": 1,
                "events.event_type": 1,
                "events.data": 1,
            },
        ),
        {},
    )


@pytest.mark.asyncio
async def test_fork_session_continues_when_checkpoint_clone_fails(monkeypatch) -> None:
    source_events = [
        {
            "event_type": "user:message",
            "data": {"content": "hello", "message_id": "run-1:user"},
            "timestamp": "2026-01-01T00:00:00Z",
        },
        {
            "event_type": "message:chunk",
            "data": {"content": "hi"},
            "timestamp": "2026-01-01T00:00:01Z",
        },
        {
            "event_type": "message:chunk",
            "data": {"content": " there"},
            "timestamp": "2026-01-01T00:00:02Z",
        },
        {
            "event_type": "done",
            "data": {"status": "completed"},
            "timestamp": "2026-01-01T00:00:03Z",
        },
    ]
    manager = SessionManager()
    storage = _FakeSessionStorage()
    manager.storage = storage
    manager._trace_storage = SimpleNamespace(
        collection=_FakeTraceCollection(
            [
                {
                    "run_id": "run-1",
                    "trace_id": "trace-1",
                    "session_id": "source",
                    "user_id": "user",
                    "events": source_events,
                    "event_count": len(source_events),
                    "status": "completed",
                    "started_at": 1,
                }
            ]
        )
    )

    async def _get_session(session_id):
        return Session(id=session_id, user_id="user", name="Source", metadata={})

    async def _resolve_target(_session_id, _message_id):
        return {
            "run_id": "run-1",
            "target_type": "assistant",
            "turn_index": 1,
            "completed_run_ids": ["run-1"],
        }

    async def _fail_clone(*_args, **_kwargs):
        raise ValueError("missing checkpoint")

    seeded_messages = []

    async def _seed_checkpoint(_thread_id, messages):
        seeded_messages.extend(messages)
        return 1

    manager.get_session = _get_session
    manager._resolve_fork_target = _resolve_target
    monkeypatch.setattr("src.infra.session.manager.clone_checkpoints_for_fork", _fail_clone)
    monkeypatch.setattr("src.infra.session.manager.seed_checkpoint_from_messages", _seed_checkpoint)

    result = await manager.fork_session_from_message("source", "run-1", "user")

    assert result["session"].id == "target"
    assert result["copied_checkpoint_count"] == 1
    assert result["copied_trace_count"] == 1
    assert storage.deleted_session_ids == []

    inserted_trace = manager.trace_storage.collection.inserted_docs[0]
    assert inserted_trace["session_id"] == "target"
    assert inserted_trace["user_id"] == "user"
    assert inserted_trace["events"] == source_events
    assert inserted_trace["event_count"] == len(source_events)
    assert [type(message).__name__ for message in seeded_messages] == [
        "HumanMessage",
        "AIMessage",
    ]
    assert seeded_messages[0].content == "hello"
    assert seeded_messages[1].content == "hi there"
