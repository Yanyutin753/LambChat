"""Delta recovery keeps the upstream history while batching duplicate seed probes."""

import copy
import re
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.serde.types import _DeltaSnapshot

from src.infra.storage import checkpoint


class DeltaDatabase:
    """Small relational fixture shared by the upstream and application saver."""

    def __init__(self):
        self.checkpoints = []
        self.blobs = {}
        self.writes = []
        self.queries = []
        self.probes = 0
        self.serde = JsonPlusSerializer()
        self.result = []

    def add_checkpoint(self, cid, parent, versions=None, inline=None, *, thread="thread", ns=""):
        self.checkpoints.append(
            {
                "thread": thread,
                "ns": ns,
                "id": cid,
                "parent": parent,
                "versions": versions or {},
                "inline": inline or {},
            }
        )

    def add_blob(self, channel, version, value, *, empty=False, thread="thread", ns=""):
        self.blobs[thread, ns, channel, version] = (
            ("empty", b"") if empty else self.serde.dumps_typed(value)
        )

    def add_write(
        self, cid, channel, value, *, task="task", path="", idx=0, thread="thread", ns=""
    ):
        kind, blob = self.serde.dumps_typed(value)
        self.writes.append(
            {
                "thread": thread,
                "ns": ns,
                "checkpoint_id": cid,
                "channel": channel,
                "type": kind,
                "blob": blob,
                "task_id": task,
                "task_path": path,
                "idx": idx,
            }
        )

    @asynccontextmanager
    async def cursor(self, **_kwargs):
        yield self

    async def execute(self, sql, params):
        self.queries.append((sql, copy.deepcopy(params)))
        if "AS ver_0" in sql:
            count = len(re.findall(r"AS ver_\d+", sql))
            correlated = "EXISTS" in sql
            stride = 4 if correlated else 2
            channels = [params[index * stride] for index in range(count)]
            thread, ns, before, limit = params[count * stride :]
            include_cursor = "checkpoint_id <= %s" in sql
            rows = sorted(
                (
                    row
                    for row in self.checkpoints
                    if row["thread"] == thread
                    and row["ns"] == ns
                    and (row["id"] <= before if include_cursor else row["id"] < before)
                ),
                key=lambda row: row["id"],
                reverse=True,
            )[:limit]
            self.result = []
            for row in rows:
                projected = {"checkpoint_id": row["id"], "parent_checkpoint_id": row["parent"]}
                for index, channel in enumerate(channels):
                    version = row["versions"].get(channel)
                    projected[f"ver_{index}"] = version
                    projected[f"inline_{index}"] = row["inline"].get(channel)
                    if correlated:
                        self.probes += 1
                        blob = self.blobs.get((thread, ns, channel, version))
                        projected[f"hb_{index}"] = bool(blob and blob[0] != "empty")
                self.result.append(projected)
        elif "FROM checkpoint_writes" not in sql and "_kind" not in sql:
            # Batched relational membership, rather than one correlated lookup per row.
            thread, ns, channels, versions = params
            pairs = list(zip(channels, versions, strict=True))
            assert len(pairs) == len(set(pairs)), (
                "seed probes must deduplicate channel/version pairs"
            )
            self.probes += len(pairs)
            self.result = [
                {"channel": channel, "version": version}
                for channel, version in pairs
                if (blob := self.blobs.get((thread, ns, channel, version))) and blob[0] != "empty"
            ]
        else:
            self.result = []
            offset = 0
            for branch in sql.split(" UNION ALL "):
                thread, ns, channel, value = params[offset : offset + 4]
                offset += 4
                if "FROM checkpoint_writes" in branch:
                    for row in reversed(
                        self.writes
                    ):  # SQL row order is deliberately not write order.
                        if (
                            row["thread"] == thread
                            and row["ns"] == ns
                            and row["channel"] == channel
                            and row["checkpoint_id"] in value
                        ):
                            self.result.append({**row, "_kind": "w", "version": None})
                elif (blob := self.blobs.get((thread, ns, channel, value))) is not None:
                    self.result.append(
                        {
                            "_kind": "b",
                            "channel": channel,
                            "version": value,
                            "type": blob[0],
                            "blob": blob[1],
                        }
                    )
        return self

    async def fetchall(self):
        return self.result


class FakePool:
    check_connection = staticmethod(lambda _connection: None)

    def __init__(self, *_args, **_kwargs):
        pass

    async def open(self, **_kwargs):
        pass

    async def close(self):
        pass


async def application_saver(monkeypatch, database):
    monkeypatch.setattr("psycopg_pool.AsyncConnectionPool", FakePool)
    monkeypatch.setattr(AsyncPostgresSaver, "setup", AsyncMock())
    monkeypatch.setattr(checkpoint, "_pg_checkpointer", None)
    monkeypatch.setattr(checkpoint, "_pg_checkpointer_pool", None)
    saver = await checkpoint._create_pg_checkpointer()
    assert saver is not None
    saver._cursor = database.cursor
    saver.aget_tuple = AsyncMock(
        return_value=SimpleNamespace(
            config={
                "configurable": {
                    "thread_id": "thread",
                    "checkpoint_ns": "",
                    "checkpoint_id": "target",
                }
            }
        )
    )
    return saver


def upstream_saver(database):
    saver = AsyncPostgresSaver(object())
    saver._cursor = database.cursor
    saver.aget_tuple = AsyncMock(
        return_value=SimpleNamespace(
            config={
                "configurable": {
                    "thread_id": "thread",
                    "checkpoint_ns": "",
                    "checkpoint_id": "target",
                }
            }
        )
    )
    return saver


def config(cid="target", *, thread="thread", ns=""):
    return {
        "configurable": {
            "thread_id": thread,
            "checkpoint_ns": ns,
            **({"checkpoint_id": cid} if cid is not None else {}),
        }
    }


@pytest.mark.parametrize("rows", [1, 1000])
async def test_delta_seed_probe_work_depends_on_distinct_versions_not_checkpoints(
    monkeypatch, rows
):
    db = DeltaDatabase()
    parent = None
    for index in range(rows):
        cid = f"c{index:05}"
        db.add_checkpoint(cid, parent, {"messages": "m-version", "files": "f-version"})
        parent = cid
    db.add_checkpoint("target", parent, {"messages": "m-version", "files": "f-version"})
    saver = await application_saver(monkeypatch, db)

    actual = await saver.aget_delta_channel_history(config=config(), channels=["messages", "files"])

    assert actual == {"messages": {"writes": []}, "files": {"writes": []}}
    assert db.probes == 2
    assert not any("EXISTS" in sql for sql, _params in db.queries)


@pytest.mark.parametrize(
    "seed,inline,empty",
    [
        (_DeltaSnapshot([{"id": "seed", "content": "all original messages"}]), True, False),
        ([{"id": "legacy", "content": "pre-delta blob"}], None, False),
        (None, False, False),
        (None, 0, False),
        (None, "", False),
        (None, True, False),
        (None, None, True),
    ],
)
async def test_delta_recovery_matches_upstream_for_blob_inline_and_empty_seeds(
    monkeypatch, seed, inline, empty
):
    db = DeltaDatabase()
    db.add_checkpoint("c0", None, {"messages": "old"}, {"messages": "old inline"})
    db.add_checkpoint("c1", "c0", {"messages": "seed"}, {"messages": inline})
    db.add_checkpoint("target", "c1")
    if seed is not None or empty:
        db.add_blob("messages", "seed", seed, empty=empty)
    db.add_write("c0", "messages", ["root write"])
    db.add_write("c1", "messages", ["later task"], task="z", idx=2)
    db.add_write("c1", "messages", ["first task"], task="a", idx=0)
    db.add_write("target", "messages", ["target writes must be excluded"])
    reference_db = copy.deepcopy(db)
    expected = await upstream_saver(reference_db).aget_delta_channel_history(
        config=config(), channels=["messages"]
    )
    saver = await application_saver(monkeypatch, db)

    actual = await saver.aget_delta_channel_history(config=config(), channels=["messages"])

    assert actual == expected
    expected_seed = seed if seed is not None else inline if inline is not None else "old inline"
    assert actual["messages"]["seed"] == expected_seed
    assert actual["messages"]["writes"][-1] == ("z", "messages", ["later task"])
    assert not any("EXISTS" in sql for sql, _params in db.queries)


async def test_delta_channels_follow_parents_not_sibling_versions_and_keep_owner_namespace(
    monkeypatch,
):
    db = DeltaDatabase()
    db.add_checkpoint("c0", None, {"files": "files-seed"})
    db.add_blob("files", "files-seed", {"/file": "complete bytes"})
    db.add_checkpoint("c1", "c0", {"messages": "message-seed"})
    db.add_blob("messages", "message-seed", ["correct branch"])
    db.add_checkpoint("sibling", "c0", {"messages": "sibling-seed"})
    db.add_blob("messages", "sibling-seed", ["wrong branch"])
    db.add_checkpoint("target", "c1")
    db.add_write("c0", "files", {"old": "file"})
    db.add_write("c1", "files", {"new": "file"})
    db.add_write("sibling", "messages", ["sibling write"])
    db.add_blob("messages", "message-seed", ["foreign"], thread="other")
    db.add_blob("files", "files-seed", {"foreign": "namespace"}, ns="other")
    expected = await upstream_saver(copy.deepcopy(db)).aget_delta_channel_history(
        config=config(), channels=["messages", "files"]
    )
    saver = await application_saver(monkeypatch, db)

    actual = await saver.aget_delta_channel_history(config=config(), channels=["messages", "files"])

    assert actual == expected
    assert actual["messages"]["seed"] == ["correct branch"]
    assert actual["files"]["seed"] == {"/file": "complete bytes"}
    assert not any("EXISTS" in sql for sql, _params in db.queries)


async def test_delta_history_walks_all_pages_and_never_caches_fresh_writes(monkeypatch):
    db = DeltaDatabase()
    parent = None
    for index in range(1100):
        cid = f"c{index:05}"
        db.add_checkpoint(cid, parent, {"messages": "same-version"})
        db.add_write(cid, "messages", [f"message-{index}"])
        parent = cid
    db.add_checkpoint("target", parent, {"messages": "same-version"})
    expected = await upstream_saver(copy.deepcopy(db)).aget_delta_channel_history(
        config=config(), channels=["messages"]
    )
    saver = await application_saver(monkeypatch, db)

    first = await saver.aget_delta_channel_history(config=config(), channels=["messages"])
    db.add_write(parent, "messages", ["fresh write"], task="zz", idx=1)
    second = await saver.aget_delta_channel_history(config=config(), channels=["messages"])

    assert first == expected
    assert len(first["messages"]["writes"]) == 1100
    assert second["messages"]["writes"][-1] == ("zz", "messages", ["fresh write"])
    assert db.probes == 4  # Two pages, one distinct version each, on both requests.


async def test_delta_history_starts_at_target_and_skips_newer_checkpoints(monkeypatch):
    db = DeltaDatabase()
    db.add_checkpoint("c0", None, {"messages": "seed"}, {"messages": "full seed"})
    db.add_checkpoint("target", "c0")
    for index in range(1100):
        db.add_checkpoint(f"z{index:05}", None, {"messages": f"newer-{index}"})
    expected = await upstream_saver(copy.deepcopy(db)).aget_delta_channel_history(
        config=config(), channels=["messages"]
    )
    saver = await application_saver(monkeypatch, db)

    actual = await saver.aget_delta_channel_history(config=config(), channels=["messages"])

    assert actual == expected == {"messages": {"writes": [], "seed": "full seed"}}
    assert db.probes == 1
    assert sum("AS ver_0" in sql for sql, _params in db.queries) == 1
    assert db.queries[0][1][-2] == "target"


async def test_delta_history_replays_task_paths_before_task_ids(monkeypatch):
    db = DeltaDatabase()
    db.add_checkpoint("c0", None)
    db.add_checkpoint("target", "c0")
    db.add_write("c0", "messages", ["second"], task="a", path="2")
    db.add_write("c0", "messages", ["first"], task="z", path="1")
    expected = await upstream_saver(copy.deepcopy(db)).aget_delta_channel_history(
        config=config(), channels=["messages"]
    )
    saver = await application_saver(monkeypatch, db)

    actual = await saver.aget_delta_channel_history(config=config(), channels=["messages"])

    assert (
        actual
        == expected
        == {"messages": {"writes": [("z", "messages", ["first"]), ("a", "messages", ["second"])]}}
    )


async def test_delta_empty_channels_and_missing_latest_checkpoint_skip_queries(monkeypatch):
    db = DeltaDatabase()
    saver = await application_saver(monkeypatch, db)
    saver.aget_tuple.return_value = None

    assert await saver.aget_delta_channel_history(config=config(), channels=[]) == {}
    assert await saver.aget_delta_channel_history(config=config(None), channels=["messages"]) == {
        "messages": {"writes": []}
    }
    assert db.queries == []


async def test_delta_latest_config_resolves_target_without_altering_config(monkeypatch):
    db = DeltaDatabase()
    db.add_checkpoint("c0", None, {"messages": "seed"}, {"messages": "full seed"})
    db.add_checkpoint("target", "c0")
    saver = await application_saver(monkeypatch, db)
    requested = config(None)
    original = copy.deepcopy(requested)

    actual = await saver.aget_delta_channel_history(config=requested, channels=["messages"])

    assert actual == {"messages": {"writes": [], "seed": "full seed"}}
    saver.aget_tuple.assert_awaited_once_with(original)
    assert requested == original
    assert not any("EXISTS" in sql for sql, _params in db.queries)


async def test_delta_query_failure_propagates_once_without_retry(monkeypatch):
    db = DeltaDatabase()
    saver = await application_saver(monkeypatch, db)
    db.execute = AsyncMock(side_effect=RuntimeError("database unavailable"))

    with pytest.raises(RuntimeError, match="database unavailable"):
        await saver.aget_delta_channel_history(config=config(), channels=["messages"])

    assert db.execute.await_count == 1


async def test_unknown_postgres_saver_version_keeps_upstream_read_path(monkeypatch):
    monkeypatch.setattr("importlib.metadata.version", lambda _package: "99.0.0")
    db = DeltaDatabase()
    db.add_checkpoint("c0", None, {"messages": "seed"}, {"messages": "full seed"})
    db.add_checkpoint("target", "c0")
    saver = await application_saver(monkeypatch, db)

    actual = await saver.aget_delta_channel_history(config=config(), channels=["messages"])

    assert actual == {"messages": {"writes": [], "seed": "full seed"}}
    assert any("EXISTS" in sql for sql, _params in db.queries)
