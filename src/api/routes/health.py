"""
健康检查路由
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.deps import require_permissions
from src.infra.monitoring import get_memory_monitor
from src.infra.monitoring.distributed_memory_health import (
    _build_highlight_items,
    _build_memory_overview,
)
from src.kernel.config import settings
from src.kernel.schemas.agent import HealthResponse, MemoryHealthSummary

router = APIRouter()


def _format_mb(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{round(value / 1024 / 1024, 2)}MB"


def _format_growth_rows(rows: list[dict] | None) -> list[dict]:
    return [
        {
            **row,
            "size_diff": _format_mb(row.get("size_diff_bytes")),
        }
        for row in (rows or [])
    ]


def _format_allocation_rows(rows: list[dict] | None) -> list[dict]:
    return [
        {
            **row,
            "size": _format_mb(row.get("size_bytes")),
        }
        for row in (rows or [])
    ]


def _format_object_rows(rows: list[dict] | None) -> list[dict]:
    return [
        {
            **row,
            "label": f"{row['type']}={row['count']}",
        }
        for row in (rows or [])
    ]


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查"""
    summary = await get_memory_monitor().get_summary()
    return HealthResponse(
        status="ok",
        version=settings.APP_VERSION,
        memory=MemoryHealthSummary.model_validate(summary),
    )


@router.get("/ready")
async def readiness_check():
    """就绪检查"""
    return {"status": "ready"}


@router.get("/health/memory")
async def memory_health_check(
    refresh: bool = False,
    _=Depends(require_permissions("settings:manage")),
):
    """详细内存诊断"""
    from src.infra.monitoring.distributed_memory_health import (
        build_cluster_overview,
        build_instance_snapshot,
        get_instance_id,
        load_cluster_snapshots,
        publish_instance_snapshot,
    )

    diagnostics = await get_memory_monitor().get_diagnostics(refresh=refresh)
    summary = diagnostics.get("summary", {})
    last_alert = diagnostics.get("last_alert") or diagnostics.get("current_snapshot") or {}

    local_instance_id = get_instance_id()
    local_snapshot = build_instance_snapshot(
        instance_id=local_instance_id,
        summary=summary,
        details=last_alert,
    )

    try:
        await publish_instance_snapshot(local_snapshot, interval_seconds=60.0)
    except Exception:
        pass

    cluster_snapshots = await load_cluster_snapshots()

    for snapshot in cluster_snapshots:
        snapshot["is_local"] = snapshot.get("instance_id") == local_instance_id

    local_in_cluster = any(s.get("is_local") for s in cluster_snapshots)
    if not local_in_cluster:
        local_snapshot["is_local"] = True
        cluster_snapshots.append(local_snapshot)

    cluster_overview = build_cluster_overview(
        cluster_snapshots,
        local_instance_id=local_instance_id,
    )
    selected_instance = cluster_overview["selected_instance"]

    return {
        "local_instance_id": local_instance_id,
        "cluster_overview": {
            "instance_count": cluster_overview["instance_count"],
            "available_instance_count": cluster_overview["available_instance_count"],
            "suspected_leak_count": cluster_overview["suspected_leak_count"],
            "selected_instance_id": cluster_overview["selected_instance_id"],
        },
        "instances": cluster_snapshots,
        "selected_instance": selected_instance,
        "summary": summary,
        "last_alert": diagnostics.get("last_alert"),
        "last_error": diagnostics.get("last_error"),
        "current_snapshot": diagnostics.get("current_snapshot"),
        "overview": selected_instance.get("overview", _build_memory_overview(summary)),
        "highlights": selected_instance.get(
            "highlights", _build_highlight_items(summary, last_alert)
        ),
        "top_growth": selected_instance.get(
            "top_growth", _format_growth_rows(last_alert.get("top_growth"))
        ),
        "top_allocations": selected_instance.get(
            "top_allocations", _format_allocation_rows(last_alert.get("top_allocations"))
        ),
        "top_objects": selected_instance.get(
            "top_objects", _format_object_rows(last_alert.get("top_object_types"))
        ),
    }
