from __future__ import annotations

import json
from collections import deque
from datetime import datetime, timezone

import pytest

import src.infra.monitoring.distributed_memory_health as memory_health


class _FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.set_calls.append((key, value, ex))
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def keys(self, pattern: str) -> list[str]:
        assert pattern == "health:memory:instance:*"
        return sorted(self.values)

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        assert match == "health:memory:instance:*"
        del count
        keys = sorted(self.values)
        if cursor == 0:
            midpoint = max(1, len(keys) // 2)
            return (1 if len(keys) > midpoint else 0), keys[:midpoint]
        return 0, keys[max(1, len(keys) // 2) :]


class _PagedRedisClient(_FakeRedisClient):
    def __init__(self, page_size: int) -> None:
        super().__init__()
        self.page_size = page_size
        self.scan_calls = 0

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        assert match == "health:memory:instance:*"
        self.scan_calls += 1
        keys = sorted(self.values)
        start = int(cursor)
        end = min(start + self.page_size, len(keys))
        next_cursor = 0 if end >= len(keys) else end
        return next_cursor, keys[start:end]


class _ScanOnlyRedisClient(_FakeRedisClient):
    async def keys(self, pattern: str) -> list[str]:
        raise AssertionError(f"Redis KEYS must not be used for pattern {pattern}")


class _FailingRedisClient:
    async def keys(self, pattern: str) -> list[str]:
        raise RuntimeError("redis unavailable")

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int | None = None,
    ) -> tuple[int, list[str]]:
        raise RuntimeError("redis unavailable")


class _FailingKeyReadRedisClient(_FakeRedisClient):
    def __init__(self, failing_keys: set[str]) -> None:
        super().__init__()
        self.failing_keys = failing_keys

    async def get(self, key: str) -> str | None:
        if key in self.failing_keys:
            raise RuntimeError(f"failed to read {key}")
        return await super().get(key)


def _build_payload(
    *,
    instance_id: str,
    available: bool = True,
    suspected_leak: bool = False,
    growth_bytes: int = 0,
    captured_at: str = "2026-04-30T03:21:00+00:00",
    last_sample_at: str = "2026-04-30T03:20:00+00:00",
) -> dict[str, object]:
    return {
        "instance_id": instance_id,
        "captured_at": captured_at,
        "summary": {
            "available": available,
            "suspected_leak": suspected_leak,
            "growth_bytes": growth_bytes,
            "last_sample_at": last_sample_at,
        },
        "overview": {
            "status": "suspected_leak"
            if available and suspected_leak
            else ("stable" if available else "unavailable"),
            "rss": None,
            "vms": None,
            "growth": None,
            "threads": None,
            "open_files": None,
            "history_size": None,
            "last_sample_at": last_sample_at,
        },
        "highlights": [],
        "top_growth": [],
        "top_allocations": [],
        "top_objects": [],
    }


def test_get_instance_id_is_stable_within_one_process() -> None:
    instance_id_a = memory_health.get_instance_id()
    instance_id_b = memory_health.get_instance_id()

    assert instance_id_a == instance_id_b
    assert isinstance(instance_id_a, str)
    assert instance_id_a


def test_build_instance_snapshot_serializes_local_diagnostics_for_redis() -> None:
    snapshot = memory_health.build_instance_snapshot(
        instance_id="  instance-a  ",
        captured_at=datetime(2026, 4, 30, 3, 21, tzinfo=timezone.utc),
        summary={
            "available": True,
            "suspected_leak": True,
            "growth_bytes": 1024,
            "rss_bytes": 8 * 1024 * 1024,
            "vms_bytes": 16 * 1024 * 1024,
            "thread_count": 4,
            "open_file_count": 2,
            "history_size": 3,
            "last_sample_at": datetime(2026, 4, 30, 3, 20, tzinfo=timezone.utc),
        },
        details={
            "top_growth": deque(
                [
                    {"location": "src/leaky.py:10", "size_diff_bytes": 2048},
                ]
            ),
            "top_allocations": [
                {"location": "src/cache.py:5", "size_bytes": 1024},
            ],
            "top_object_types": [
                {"type": "dict", "count": 12},
            ],
        },
    )

    assert snapshot == {
        "instance_id": "instance-a",
        "captured_at": "2026-04-30T03:21:00+00:00",
        "summary": {
            "available": True,
            "suspected_leak": True,
            "growth_bytes": 1024,
            "rss_bytes": 8 * 1024 * 1024,
            "vms_bytes": 16 * 1024 * 1024,
            "thread_count": 4,
            "open_file_count": 2,
            "history_size": 3,
            "last_sample_at": "2026-04-30T03:20:00+00:00",
        },
        "overview": {
            "status": "suspected_leak",
            "rss": "8.0MB",
            "vms": "16.0MB",
            "growth": "0.0MB",
            "threads": 4,
            "open_files": 2,
            "history_size": 3,
            "last_sample_at": "2026-04-30T03:20:00+00:00",
        },
        "highlights": [
            {
                "kind": "status",
                "status": "suspected_leak",
                "severity": "warning",
            },
            {
                "kind": "top_growth",
                "location": "src/leaky.py:10",
                "size_diff": "0.0MB",
            },
            {
                "kind": "top_allocation",
                "location": "src/cache.py:5",
                "size": "0.0MB",
            },
            {
                "kind": "top_object_type",
                "type": "dict",
                "count": 12,
            },
        ],
        "top_growth": [
            {
                "location": "src/leaky.py:10",
                "size_diff_bytes": 2048,
                "size_diff": "0.0MB",
            },
        ],
        "top_allocations": [
            {
                "location": "src/cache.py:5",
                "size_bytes": 1024,
                "size": "0.0MB",
            },
        ],
        "top_objects": [
            {
                "type": "dict",
                "count": 12,
                "label": "dict=12",
            },
        ],
    }
    assert json.loads(json.dumps(snapshot)) == snapshot


def test_build_instance_snapshot_tolerates_incomplete_detail_rows() -> None:
    snapshot = memory_health.build_instance_snapshot(
        instance_id="instance-a",
        captured_at="2026-04-30T03:21:00+00:00",
        summary={"available": True, "suspected_leak": False},
        details={
            "top_growth": [{}],
            "top_allocations": [{}],
            "top_object_types": [{}],
        },
    )

    assert snapshot["highlights"] == [
        {
            "kind": "status",
            "status": "stable",
            "severity": "info",
        }
    ]
    assert snapshot["top_growth"] == [{"size_diff": None}]
    assert snapshot["top_allocations"] == [{"size": None}]
    assert snapshot["top_objects"] == [{"label": None}]


def test_build_instance_snapshot_tolerates_non_mapping_or_non_sequence_details() -> None:
    list_details_snapshot = memory_health.build_instance_snapshot(
        instance_id="instance-a",
        captured_at="2026-04-30T03:21:00+00:00",
        summary={"available": True, "suspected_leak": False},
        details=[],
    )
    dict_row_snapshot = memory_health.build_instance_snapshot(
        instance_id="instance-b",
        captured_at="2026-04-30T03:21:00+00:00",
        summary={"available": True, "suspected_leak": False},
        details={
            "top_growth": {"location": "src/leaky.py:10"},
            "top_allocations": {"location": "src/cache.py:5"},
            "top_object_types": {"type": "dict", "count": 3},
        },
    )

    assert list_details_snapshot["highlights"] == [
        {
            "kind": "status",
            "status": "stable",
            "severity": "info",
        }
    ]
    assert list_details_snapshot["top_growth"] == []
    assert list_details_snapshot["top_allocations"] == []
    assert list_details_snapshot["top_objects"] == []

    assert dict_row_snapshot["highlights"] == [
        {
            "kind": "status",
            "status": "stable",
            "severity": "info",
        }
    ]
    assert dict_row_snapshot["top_growth"] == []
    assert dict_row_snapshot["top_allocations"] == []
    assert dict_row_snapshot["top_objects"] == []


@pytest.mark.asyncio
async def test_publish_and_load_cluster_snapshots_use_redis_safe_payloads() -> None:
    redis_client = _FakeRedisClient()
    snapshot = memory_health.build_instance_snapshot(
        instance_id="instance-a",
        captured_at="2026-04-30T03:21:00+00:00",
        summary={"available": True, "growth_bytes": 2048},
        details={"top_growth": []},
    )

    await memory_health.publish_instance_snapshot(
        snapshot,
        interval_seconds=75,
        redis_client=redis_client,
    )

    assert redis_client.set_calls == [
        (
            "health:memory:instance:instance-a",
            json.dumps(snapshot),
            150,
        )
    ]

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert loaded == [snapshot]


@pytest.mark.asyncio
async def test_publish_instance_snapshot_offloads_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    redis_client = _FakeRedisClient()
    snapshot = memory_health.build_instance_snapshot(
        instance_id="instance-a",
        captured_at="2026-04-30T03:21:00+00:00",
        summary={"available": True, "growth_bytes": 2048},
        details={"top_growth": []},
    )

    async def _fake_run_long_blocking_io(func, /, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        memory_health, "run_long_blocking_io", _fake_run_long_blocking_io, raising=False
    )

    await memory_health.publish_instance_snapshot(
        snapshot,
        interval_seconds=75,
        redis_client=redis_client,
    )

    assert calls == [json.dumps]
    assert redis_client.set_calls[0][1] == json.dumps(snapshot)


@pytest.mark.asyncio
async def test_load_cluster_snapshots_offloads_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    redis_client = _FakeRedisClient()
    instance_a = _build_payload(instance_id="instance-a")
    redis_client.values = {
        "health:memory:instance:instance-a": json.dumps(instance_a),
    }

    async def _fake_run_long_blocking_io(func, /, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(
        memory_health, "run_long_blocking_io", _fake_run_long_blocking_io, raising=False
    )

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert loaded == [instance_a]
    assert calls == [json.loads]


@pytest.mark.asyncio
async def test_load_cluster_snapshots_scans_without_blocking_redis_keys() -> None:
    redis_client = _ScanOnlyRedisClient()
    instance_a = _build_payload(instance_id="instance-a")
    instance_b = _build_payload(instance_id="instance-b")
    redis_client.values = {
        "health:memory:instance:instance-b": json.dumps(instance_b),
        "health:memory:instance:instance-a": json.dumps(instance_a),
    }

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert loaded == [instance_a, instance_b]


@pytest.mark.asyncio
async def test_load_cluster_snapshots_limits_scanned_instance_keys() -> None:
    redis_client = _PagedRedisClient(page_size=25)
    redis_client.values = {
        f"health:memory:instance:instance-{index:03d}": json.dumps(
            _build_payload(instance_id=f"instance-{index:03d}")
        )
        for index in range(memory_health.CLUSTER_SNAPSHOT_SCAN_LIMIT + 50)
    }

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert len(loaded) == memory_health.CLUSTER_SNAPSHOT_SCAN_LIMIT
    assert loaded[-1]["instance_id"] == (
        f"instance-{memory_health.CLUSTER_SNAPSHOT_SCAN_LIMIT - 1:03d}"
    )
    assert redis_client.scan_calls < 10


@pytest.mark.asyncio
async def test_publish_instance_snapshot_fills_missing_instance_id_for_round_trip() -> None:
    redis_client = _FakeRedisClient()
    snapshot = {
        "instance_id": "",
        "captured_at": "2026-04-30T03:21:00+00:00",
        "summary": {"available": True},
        "overview": {"status": "stable"},
        "highlights": [],
        "top_growth": [],
        "top_allocations": [],
        "top_objects": [],
    }

    published = await memory_health.publish_instance_snapshot(
        snapshot,
        interval_seconds=75,
        redis_client=redis_client,
    )
    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert published["instance_id"]
    assert json.loads(redis_client.set_calls[0][1])["instance_id"] == published["instance_id"]
    assert loaded == [published]


@pytest.mark.asyncio
async def test_publish_instance_snapshot_replaces_whitespace_instance_id_for_round_trip() -> None:
    redis_client = _FakeRedisClient()
    snapshot = {
        "instance_id": "   ",
        "captured_at": "2026-04-30T03:21:00+00:00",
        "summary": {"available": True},
        "overview": {"status": "stable"},
        "highlights": [],
        "top_growth": [],
        "top_allocations": [],
        "top_objects": [],
    }

    published = await memory_health.publish_instance_snapshot(
        snapshot,
        interval_seconds=75,
        redis_client=redis_client,
    )
    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert published["instance_id"]
    assert published["instance_id"] != "   "
    assert json.loads(redis_client.set_calls[0][1])["instance_id"] == published["instance_id"]
    assert loaded == [published]


@pytest.mark.asyncio
async def test_load_cluster_snapshots_skips_invalid_records_and_keeps_valid_ones() -> None:
    redis_client = _FakeRedisClient()
    valid_snapshot = _build_payload(instance_id="instance-a")
    redis_client.values = {
        "health:memory:instance:broken": "{not-json",
        "health:memory:instance:instance-a": json.dumps(valid_snapshot),
    }

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert loaded == [valid_snapshot]


@pytest.mark.asyncio
async def test_load_cluster_snapshots_skips_failed_key_reads_and_keeps_valid_ones() -> None:
    redis_client = _FailingKeyReadRedisClient({"health:memory:instance:broken-read"})
    valid_snapshot = _build_payload(instance_id="instance-a")
    redis_client.values = {
        "health:memory:instance:broken-read": json.dumps(_build_payload(instance_id="instance-b")),
        "health:memory:instance:instance-a": json.dumps(valid_snapshot),
    }

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert loaded == [valid_snapshot]


@pytest.mark.asyncio
async def test_load_cluster_snapshots_skips_structurally_invalid_dict_payloads() -> None:
    redis_client = _FakeRedisClient()
    valid_snapshot = _build_payload(instance_id="instance-a")
    redis_client.values = {
        "health:memory:instance:empty": json.dumps({}),
        "health:memory:instance:missing-instance-id": json.dumps(
            {"captured_at": "2026-04-30T03:21:00+00:00", "summary": {}}
        ),
        "health:memory:instance:invalid-summary": json.dumps(
            {"instance_id": "invalid-summary", "summary": []}
        ),
        "health:memory:instance:invalid-instance-id-type": json.dumps(
            {"instance_id": 123, "summary": {}}
        ),
        "health:memory:instance:instance-a": json.dumps(valid_snapshot),
    }

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert loaded == [valid_snapshot]


@pytest.mark.asyncio
async def test_load_cluster_snapshots_normalizes_padded_instance_ids_and_selection_matches() -> (
    None
):
    redis_client = _FakeRedisClient()
    redis_client.values = {
        "health:memory:instance:padded": json.dumps(_build_payload(instance_id="  instance-a  "))
    }

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)
    selected_by_request = memory_health.select_instance_snapshot(
        loaded,
        requested_instance_id="  instance-a  ",
    )
    selected_by_local = memory_health.select_instance_snapshot(
        loaded,
        local_instance_id="  instance-a  ",
    )

    assert loaded[0]["instance_id"] == "instance-a"
    assert selected_by_request == loaded[0]
    assert selected_by_local == loaded[0]


@pytest.mark.asyncio
async def test_load_cluster_snapshots_deduplicates_padded_and_normalized_keys_for_same_instance() -> (
    None
):
    redis_client = _FakeRedisClient()
    redis_client.values = {
        "health:memory:instance:legacy-padded": json.dumps(
            _build_payload(
                instance_id="  instance-a  ",
                captured_at="2026-04-30T03:20:00+00:00",
            )
        ),
        "health:memory:instance:normalized": json.dumps(
            _build_payload(
                instance_id="instance-a",
                captured_at="2026-04-30T03:21:00+00:00",
                growth_bytes=99,
            )
        ),
    }

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert loaded == [
        _build_payload(
            instance_id="instance-a",
            captured_at="2026-04-30T03:21:00+00:00",
            growth_bytes=99,
        )
    ]


@pytest.mark.asyncio
async def test_load_cluster_snapshots_deduplicates_mixed_aware_and_naive_timestamps() -> None:
    redis_client = _FakeRedisClient()
    redis_client.values = {
        "health:memory:instance:aware": json.dumps(
            _build_payload(
                instance_id="instance-a",
                captured_at="2026-04-30T03:21:00+00:00",
                growth_bytes=10,
            )
        ),
        "health:memory:instance:naive": json.dumps(
            _build_payload(
                instance_id="instance-a",
                captured_at="2026-04-30T03:22:00",
                growth_bytes=20,
            )
        ),
    }

    loaded = await memory_health.load_cluster_snapshots(redis_client=redis_client)

    assert loaded == [
        _build_payload(
            instance_id="instance-a",
            captured_at="2026-04-30T03:22:00",
            growth_bytes=20,
        )
    ]


def test_build_cluster_overview_aggregates_multiple_instance_payloads() -> None:
    instance_payloads = [
        _build_payload(
            instance_id="instance-b", available=True, suspected_leak=True, growth_bytes=99
        ),
        _build_payload(
            instance_id="instance-a", available=True, suspected_leak=False, growth_bytes=5
        ),
        _build_payload(
            instance_id="instance-c", available=False, suspected_leak=False, growth_bytes=0
        ),
    ]

    overview = memory_health.build_cluster_overview(
        instance_payloads,
        local_instance_id="instance-a",
    )

    assert overview["instance_count"] == 3
    assert overview["available_instance_count"] == 2
    assert overview["suspected_leak_count"] == 1
    assert overview["selected_instance_id"] == "instance-a"
    assert [item["instance_id"] for item in overview["instances"]] == [
        "instance-a",
        "instance-b",
        "instance-c",
    ]


def test_select_instance_snapshot_prefers_requested_then_local_then_fallback() -> None:
    snapshots = [
        _build_payload(instance_id="instance-b"),
        _build_payload(instance_id="instance-a"),
    ]

    assert (
        memory_health.select_instance_snapshot(
            snapshots,
            requested_instance_id="instance-b",
            local_instance_id="instance-a",
        )
        == snapshots[0]
    )
    assert (
        memory_health.select_instance_snapshot(
            snapshots,
            local_instance_id="instance-a",
        )
        == snapshots[1]
    )
    assert (
        memory_health.select_instance_snapshot(
            snapshots,
            requested_instance_id="missing",
            local_instance_id="missing",
        )
        == snapshots[1]
    )


def test_select_instance_snapshot_ignores_invalid_snapshots_for_fallback() -> None:
    valid_snapshot = _build_payload(instance_id="instance-a")

    assert (
        memory_health.select_instance_snapshot(
            [{}, valid_snapshot],
            requested_instance_id="missing",
            local_instance_id="missing",
        )
        == valid_snapshot
    )


def test_build_cluster_overview_normalizes_padded_instance_ids_without_redis_round_trip() -> None:
    padded_snapshot = memory_health.build_instance_snapshot(
        instance_id="  instance-a  ",
        captured_at="2026-04-30T03:21:00+00:00",
        summary={"available": True, "suspected_leak": False},
        details={},
    )

    overview = memory_health.build_cluster_overview(
        [padded_snapshot],
        requested_instance_id="  instance-a  ",
        local_instance_id="  instance-a  ",
    )

    assert padded_snapshot["instance_id"] == "instance-a"
    assert overview["selected_instance_id"] == "instance-a"
    assert overview["instances"][0]["instance_id"] == "instance-a"


@pytest.mark.asyncio
async def test_load_cluster_snapshots_returns_empty_list_when_redis_fails() -> None:
    loaded = await memory_health.load_cluster_snapshots(redis_client=_FailingRedisClient())

    assert loaded == []
    assert memory_health.build_cluster_overview(loaded)["instance_count"] == 0
