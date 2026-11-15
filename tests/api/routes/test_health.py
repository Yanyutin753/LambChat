from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import src.infra.monitoring.distributed_memory_health as distributed_memory_health
from src.api.routes import health as health_routes


class _FakeMonitor:
    def __init__(self) -> None:
        self.refresh_calls: list[bool] = []

    async def get_summary(self) -> dict[str, object]:
        return {
            "available": True,
            "rss_bytes": 123 * 1024 * 1024,
            "vms_bytes": 456 * 1024 * 1024,
            "thread_count": 7,
            "open_file_count": 2,
            "history_size": 3,
            "suspected_leak": True,
            "growth_bytes": 77 * 1024 * 1024,
            "baseline_reset_at": "2026-04-30T12:05:00+00:00",
            "checkpointer": {
                "configured_backend": "mongodb",
                "memory_saver_cache_active": True,
                "memory_saver_cache_size": 2,
            },
        }

    async def get_diagnostics(self, refresh: bool = False) -> dict[str, object]:
        self.refresh_calls.append(refresh)
        return {
            "summary": await self.get_summary(),
            "last_alert": {
                "captured_at": "2026-04-30T12:00:00+00:00",
                "top_growth": [
                    {"location": "src/leaky.py:88", "size_diff_bytes": 999 * 1024 * 1024}
                ],
                "top_allocations": [
                    {"location": "src/cache.py:21", "size_bytes": 222 * 1024 * 1024}
                ],
                "top_object_types": [{"type": "dict", "count": 4200}],
            },
        }


@pytest.fixture(autouse=True)
def _mock_distributed_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(distributed_memory_health, "get_instance_id", lambda: "test-instance")
    monkeypatch.setattr(
        distributed_memory_health, "load_cluster_snapshots", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        distributed_memory_health, "publish_instance_snapshot", AsyncMock(return_value={})
    )


@pytest.mark.asyncio
async def test_health_route_returns_memory_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.health_check()

    assert response.status == "ok"
    assert response.memory is not None
    assert response.memory.rss_bytes == 123 * 1024 * 1024
    assert response.memory.suspected_leak is True
    assert response.memory.checkpointer["memory_saver_cache_size"] == 2


@pytest.mark.asyncio
async def test_memory_health_route_returns_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.memory_health_check()

    assert response["summary"]["rss_bytes"] == 123 * 1024 * 1024
    assert response["last_alert"]["top_growth"][0]["location"] == "src/leaky.py:88"


@pytest.mark.asyncio
async def test_memory_health_route_returns_human_readable_overview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.memory_health_check()

    assert response["overview"]["status"] == "suspected_leak"
    assert response["overview"]["rss"] == "123.0MB"
    assert response["overview"]["growth"] == "77.0MB"
    assert response["highlights"][0]["kind"] == "status"
    assert response["highlights"][0]["status"] == "suspected_leak"
    assert response["top_growth"][0]["size_diff"] == "999.0MB"
    assert response["top_allocations"][0]["size"] == "222.0MB"
    assert response["top_objects"][0]["label"] == "dict=4200"


@pytest.mark.asyncio
async def test_memory_health_route_returns_structured_highlights(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.memory_health_check()

    assert response["highlights"] == [
        {
            "kind": "status",
            "status": "suspected_leak",
            "severity": "warning",
        },
        {
            "kind": "top_growth",
            "location": "src/leaky.py:88",
            "size_diff": "999.0MB",
        },
        {
            "kind": "top_allocation",
            "location": "src/cache.py:21",
            "size": "222.0MB",
        },
        {
            "kind": "top_object_type",
            "type": "dict",
            "count": 4200,
        },
    ]


@pytest.mark.asyncio
async def test_memory_health_route_returns_baseline_reset_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())

    response = await health_routes.memory_health_check()

    assert response["summary"]["baseline_reset_at"] == "2026-04-30T12:05:00+00:00"


@pytest.mark.asyncio
async def test_memory_health_route_defaults_to_cached_diagnostics_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitor = _FakeMonitor()
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: monitor)

    await health_routes.memory_health_check()

    assert monitor.refresh_calls == [False]


@pytest.mark.asyncio
async def test_memory_health_route_supports_explicit_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitor = _FakeMonitor()
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: monitor)

    await health_routes.memory_health_check(refresh=True)

    assert monitor.refresh_calls == [True]


_FAKE_CLUSTER_INSTANCES = [
    {
        "instance_id": "local-a",
        "is_local": True,
        "overview": {
            "status": "stable",
            "rss": "123.0MB",
            "vms": None,
            "growth": None,
            "threads": None,
            "open_files": None,
            "history_size": None,
            "last_sample_at": None,
        },
        "highlights": [{"kind": "status", "status": "stable", "severity": "info"}],
        "top_growth": [],
        "top_allocations": [],
        "top_objects": [],
        "summary": {"available": True, "rss_bytes": 123 * 1024 * 1024, "suspected_leak": False},
    },
    {
        "instance_id": "remote-b",
        "is_local": False,
        "overview": {
            "status": "suspected_leak",
            "rss": "456.0MB",
            "vms": None,
            "growth": None,
            "threads": None,
            "open_files": None,
            "history_size": None,
            "last_sample_at": None,
        },
        "highlights": [{"kind": "status", "status": "suspected_leak", "severity": "warning"}],
        "top_growth": [
            {
                "location": "src/leaky.py:88",
                "size_diff_bytes": 999 * 1024 * 1024,
                "size_diff": "999.0MB",
            }
        ],
        "top_allocations": [],
        "top_objects": [],
        "summary": {"available": True, "rss_bytes": 456 * 1024 * 1024, "suspected_leak": True},
    },
]


@pytest.mark.asyncio
async def test_memory_health_route_returns_cluster_fields_when_instances_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())
    monkeypatch.setattr(
        distributed_memory_health,
        "get_instance_id",
        lambda: "local-a",
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "load_cluster_snapshots",
        AsyncMock(return_value=[inst.copy() for inst in _FAKE_CLUSTER_INSTANCES]),
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        AsyncMock(return_value={}),
    )

    response = await health_routes.memory_health_check()

    assert response["local_instance_id"] == "local-a"
    assert response["cluster_overview"]["instance_count"] == 2
    assert response["cluster_overview"]["available_instance_count"] == 2
    assert response["cluster_overview"]["suspected_leak_count"] == 1
    assert response["selected_instance"]["instance_id"] == "local-a"
    assert response["selected_instance"]["is_local"] is True
    assert len(response["instances"]) == 2


@pytest.mark.asyncio
async def test_memory_health_route_mirrors_selected_instance_into_top_level_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())
    monkeypatch.setattr(
        distributed_memory_health,
        "get_instance_id",
        lambda: "local-a",
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "load_cluster_snapshots",
        AsyncMock(return_value=[inst.copy() for inst in _FAKE_CLUSTER_INSTANCES]),
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        AsyncMock(return_value={}),
    )

    response = await health_routes.memory_health_check()

    selected = response["selected_instance"]
    assert response["overview"] == selected["overview"]
    assert response["highlights"] == selected["highlights"]
    assert response["top_growth"] == selected["top_growth"]
    assert response["top_allocations"] == selected["top_allocations"]
    assert response["top_objects"] == selected["top_objects"]


@pytest.mark.asyncio
async def test_memory_health_route_refresh_passes_through_to_monitor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monitor = _FakeMonitor()
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: monitor)
    monkeypatch.setattr(
        distributed_memory_health,
        "get_instance_id",
        lambda: "local-a",
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "load_cluster_snapshots",
        AsyncMock(return_value=[inst.copy() for inst in _FAKE_CLUSTER_INSTANCES]),
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        AsyncMock(return_value={}),
    )

    await health_routes.memory_health_check(refresh=True)

    assert monitor.refresh_calls == [True]


@pytest.mark.asyncio
async def test_memory_health_route_returns_local_only_when_redis_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: _FakeMonitor())
    monkeypatch.setattr(
        distributed_memory_health,
        "get_instance_id",
        lambda: "local-a",
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "load_cluster_snapshots",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        AsyncMock(side_effect=RuntimeError("redis down")),
    )

    response = await health_routes.memory_health_check()

    assert response["local_instance_id"] == "local-a"
    assert response["cluster_overview"]["instance_count"] == 1
    assert response["selected_instance"]["instance_id"] == "local-a"
    assert response["selected_instance"]["is_local"] is True
    assert response["overview"]["status"] == "suspected_leak"
    assert response["highlights"][0]["kind"] == "status"


async def test_health_exposes_sampled_run_context_without_claiming_process_idle(monkeypatch):
    monitor = _FakeMonitor()
    monitor.get_summary = AsyncMock(
        return_value={
            "available": True,
            "memory_pressure": True,
            "memory_current_bytes": 900,
            "memory_limit_bytes": 1000,
            "active_runs": 0,
            "queued_runs": 0,
            "idle_seconds": None,
            "idle_rss_change_bytes": None,
            "sampled_no_run_window_seconds": 600,
            "sampled_no_run_rss_change_bytes": -40,
            "peak_rss_bytes": 950,
            "history_window_seconds": 660,
            "process_started_at": "2026-11-15T00:00:00+00:00",
        }
    )
    monkeypatch.setattr(health_routes, "get_memory_monitor", lambda: monitor)
    response = await health_routes.health_check()
    summary = response.memory.model_dump()
    assert summary["memory_pressure"] is True
    assert summary["idle_seconds"] is None
    assert summary["sampled_no_run_window_seconds"] == 600
    assert summary["sampled_no_run_rss_change_bytes"] == -40
    assert summary["active_runs"] == 0
    assert health_routes._build_memory_overview(summary)["status"] == "memory_pressure"
    assert health_routes._build_highlight_items(summary, None)[0]["severity"] == "warning"
