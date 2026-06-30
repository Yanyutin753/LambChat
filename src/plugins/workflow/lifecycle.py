"""Lifecycle hooks for the workflow plugin."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.plugins.workflow.storage import (
    DEFAULT_MAX_EVENT_PAYLOAD_BYTES,
    WorkflowPluginStorage,
)

logger = get_logger(__name__)
PLUGIN_ID = "workflow"
DEFAULT_RUN_LOG_RETENTION_DAYS = 30


async def startup() -> None:
    """Prepare durable workflow storage and reconcile interrupted runs."""
    storage = await create_workflow_storage()
    await storage.ensure_indexes()
    recovered = 0
    while True:
        batch_count = await storage.fail_stale_running_runs()
        if not batch_count:
            break
        recovered += batch_count
    if recovered:
        logger.warning(
            "Marked %s stale async/stream workflow runs as failed after startup", recovered
        )
    retention_days = await resolve_run_log_retention_days()
    delete_terminal_run_logs_before = getattr(storage, "delete_terminal_run_logs_before", None)
    if retention_days > 0 and callable(delete_terminal_run_logs_before):
        deleted = await storage.delete_terminal_run_logs_before(
            utc_now() - timedelta(days=retention_days)
        )
        if deleted:
            logger.info("Deleted %s expired workflow run logs after startup", deleted)


async def create_workflow_storage() -> WorkflowPluginStorage:
    """Create workflow storage using runtime plugin settings."""
    max_event_payload_bytes = await resolve_max_event_payload_bytes()
    try:
        return WorkflowPluginStorage(max_event_payload_bytes=max_event_payload_bytes)
    except TypeError:
        return WorkflowPluginStorage()


async def resolve_max_event_payload_bytes() -> int:
    """Resolve the persisted debug event payload byte cap from plugin settings."""
    try:
        from src.infra.extensions.plugin_settings import PluginSettingsResolver
        from src.kernel.extensions.builtin_plugins import build_workflow_plugin_manifest

        manifest = build_workflow_plugin_manifest()
        manifest.package_data_dir = str(Path(settings.PLUGIN_DATA_PATH) / PLUGIN_ID)
        resolver = PluginSettingsResolver(plugin_id=PLUGIN_ID, manifests=(manifest,))
        raw_bytes = await resolver.get_int(
            "MAX_EVENT_PAYLOAD_BYTES",
            DEFAULT_MAX_EVENT_PAYLOAD_BYTES,
        )
    except Exception:
        raw_bytes = DEFAULT_MAX_EVENT_PAYLOAD_BYTES
    return int(raw_bytes)


async def resolve_run_log_retention_days() -> int:
    """Resolve the workflow run log retention window from plugin settings."""
    try:
        from src.infra.extensions.plugin_settings import PluginSettingsResolver
        from src.kernel.extensions.builtin_plugins import build_workflow_plugin_manifest

        manifest = build_workflow_plugin_manifest()
        manifest.package_data_dir = str(Path(settings.PLUGIN_DATA_PATH) / PLUGIN_ID)
        resolver = PluginSettingsResolver(plugin_id=PLUGIN_ID, manifests=(manifest,))
        raw_days = await resolver.get_int("RUN_LOG_RETENTION_DAYS", DEFAULT_RUN_LOG_RETENTION_DAYS)
    except Exception:
        raw_days = DEFAULT_RUN_LOG_RETENTION_DAYS
    return max(int(raw_days), 0)


def shutdown() -> None:
    """Reserved for future runtime cleanup."""
    return None


__all__ = [
    "create_workflow_storage",
    "resolve_max_event_payload_bytes",
    "resolve_run_log_retention_days",
    "shutdown",
    "startup",
]
