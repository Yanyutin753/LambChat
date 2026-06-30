"""
Runtime service orchestration for distributed listeners.

Centralizes startup/shutdown of lightweight process-local listeners that
coordinate through shared Redis/Mongo infrastructure.
"""

from __future__ import annotations

from src.agents.core.recommendations import drain_recommend_background_tasks
from src.infra.async_utils import shutdown_blocking_io_executor
from src.infra.channel.pubsub import close_channel_config_pubsub, get_channel_config_pubsub
from src.infra.llm.pubsub import get_model_config_pubsub
from src.infra.monitoring.event_loop import (
    start_event_loop_lag_monitor,
    stop_event_loop_lag_monitor,
)
from src.infra.scheduler import ScheduledJob, get_runtime_scheduler
from src.infra.scheduler.service import ScheduledTaskService
from src.infra.scheduler.storage import get_scheduled_task_storage
from src.infra.settings.pubsub import get_settings_pubsub
from src.infra.task.arq_runtime import start_arq_runtime, stop_arq_runtime
from src.infra.task.manager import get_task_manager
from src.infra.tool.cache_pubsub import (
    close_tool_cache_pubsub,
    get_tool_cache_pubsub,
)
from src.infra.tool.mcp_cache import drain_background_tasks as drain_mcp_cache_background_tasks
from src.infra.tool.mcp_global import (
    close_global_mcp_cache,
    close_mcp_cache_pubsub,
    get_mcp_cache_pubsub,
)
from src.infra.tool.mcp_global import (
    drain_background_tasks as drain_mcp_global_background_tasks,
)
from src.infra.tool.mcp_pool import close_all_connections as close_mcp_pool_connections
from src.infra.websocket import get_connection_manager
from src.kernel.config import settings


def get_memory_pubsub():
    from src.infra.memory.distributed import get_memory_pubsub

    return get_memory_pubsub()


async def close_memory_pubsub() -> None:
    from src.infra.memory.distributed import close_memory_pubsub as _close_memory_pubsub

    await _close_memory_pubsub()


async def memory_shutdown() -> None:
    from src.infra.memory.tools import shutdown

    await shutdown()


async def drain_dual_writer_event_buffer() -> None:
    from src.infra.session.dual_writer import close_dual_writer

    await close_dual_writer()


async def drain_upload_delete_tasks() -> None:
    from src.api.routes.upload import drain_upload_delete_tasks as _drain_upload_delete_tasks

    await _drain_upload_delete_tasks()


async def drain_user_s3_cleanup_tasks() -> None:
    from src.infra.user.manager import drain_s3_cleanup_tasks

    await drain_s3_cleanup_tasks()


async def drain_project_cleanup_tasks() -> None:
    from src.infra.tool.reveal_project_tool import drain_project_cleanup_tasks as _drain

    await _drain()


async def drain_llm_client_close_tasks() -> None:
    from src.infra.llm.client import LLMClient

    LLMClient.close_cached_models()
    await LLMClient.drain_close_tasks()


async def close_role_cache_redis() -> None:
    from src.infra.role.storage import close_role_cache_redis as _close_role_cache_redis

    await _close_role_cache_redis()


async def close_channel_manager_instances() -> None:
    from src.infra.channel.base import UserChannelManager

    await UserChannelManager.close_all_instances()


async def close_pubsub_hub() -> None:
    from src.infra.pubsub_hub import close_pubsub_hub as _close_pubsub_hub

    await _close_pubsub_hub()


async def close_ws_rate_limiter() -> None:
    from src.infra.websocket_rate_limiter import close_ws_rate_limiter as _close

    await _close()


async def close_s3_storage() -> None:
    from src.infra.storage.s3.service import close_storage

    await close_storage()


async def close_runtime_scheduler() -> None:
    from src.infra.scheduler.runner import drain_detached_monitors
    from src.infra.scheduler.runtime import close_runtime_scheduler as _close_runtime_scheduler
    from src.infra.scheduler.service import clear_managed_task_signatures
    from src.infra.scheduler.storage import close_scheduled_task_storage

    await drain_detached_monitors()
    await _close_runtime_scheduler()
    clear_managed_task_signatures()
    close_scheduled_task_storage()


async def cleanup_skills_storage_cache() -> None:
    from src.infra.backend.skills_store import SkillsStoreBackend

    await SkillsStoreBackend.cleanup_storage_cache()


async def close_settings_service() -> None:
    from src.infra.settings.service import SettingsService

    service = SettingsService._instance
    if service is not None:
        await service.close()


def start_memory_compaction_agent() -> None:
    from src.infra.memory.tools import start_memory_compaction_agent

    start_memory_compaction_agent()


def register_scheduled_task_reconcile_job(
    scheduled_task_service: ScheduledTaskService,
) -> None:
    """Keep process-local scheduled jobs in sync with MongoDB in multi-instance runs."""
    get_runtime_scheduler().register_job(
        ScheduledJob.from_interval(
            id="scheduled_tasks.reconcile",
            interval_seconds=30,
            handler=scheduled_task_service.load_persisted_tasks,
            name="Scheduled task reconcile",
            max_instances=1,
            coalesce=True,
        )
    )


async def start_runtime_services(
    *,
    plugin_runtime: object | None = None,
    plugin_runtime_state_storage: object | None = None,
) -> None:
    """Start distributed runtime listeners needed by the current process."""
    import asyncio

    await start_event_loop_lag_monitor()

    task_manager = get_task_manager()
    await task_manager.start_pubsub_listener()
    if plugin_runtime is None and plugin_runtime_state_storage is None:
        await start_arq_runtime()
    else:
        await start_arq_runtime(
            plugin_runtime=plugin_runtime,
            plugin_runtime_state_storage=plugin_runtime_state_storage,
        )

    # Launch all pub/sub listeners concurrently to reduce startup wall-clock time.
    settings_pubsub = get_settings_pubsub()
    model_config_pubsub = get_model_config_pubsub()
    channel_pubsub = get_channel_config_pubsub()
    tool_cache_pubsub = get_tool_cache_pubsub()
    mcp_cache_pubsub = get_mcp_cache_pubsub()
    websocket_manager = get_connection_manager()

    listeners = [
        settings_pubsub.start_listener(),
        model_config_pubsub.start_listener(),
        channel_pubsub.start_listener(),
        tool_cache_pubsub.start_listener(),
        mcp_cache_pubsub.start_listener(),
        websocket_manager.start_pubsub_listener(),
    ]
    if settings.ENABLE_MEMORY:
        listeners.append(get_memory_pubsub().start_listener())

    await asyncio.gather(
        *listeners,
    )

    if settings.ENABLE_MEMORY:
        start_memory_compaction_agent()

    if settings.ENABLE_SCHEDULED_TASK:
        # Load dynamically-created scheduled tasks from DB only when the feature is enabled.
        await get_scheduled_task_storage().ensure_indexes()
        scheduled_task_service = ScheduledTaskService()
        await scheduled_task_service.load_persisted_tasks()
        register_scheduled_task_reconcile_job(scheduled_task_service)

        get_runtime_scheduler().start()


async def stop_runtime_services() -> None:
    """Stop distributed runtime listeners in reverse dependency order."""
    await stop_event_loop_lag_monitor()

    # Close debug log file handle to prevent FD leak
    try:
        from src.infra.agent.events.debug_logger import shutdown as debug_logger_shutdown

        debug_logger_shutdown()
    except Exception:
        pass

    websocket_manager = get_connection_manager()
    await websocket_manager.stop_pubsub_listener()

    await close_mcp_cache_pubsub()
    await drain_mcp_cache_background_tasks()
    await close_global_mcp_cache()
    await drain_mcp_global_background_tasks()
    await drain_recommend_background_tasks()
    await close_mcp_pool_connections()

    await close_tool_cache_pubsub()

    await close_channel_config_pubsub()
    await close_channel_manager_instances()

    await close_runtime_scheduler()

    if settings.ENABLE_MEMORY:
        await close_memory_pubsub()
        await memory_shutdown()

    model_config_pubsub = get_model_config_pubsub()
    await model_config_pubsub.stop_listener()

    settings_pubsub = get_settings_pubsub()
    await settings_pubsub.stop_listener()

    task_manager = get_task_manager()
    await stop_arq_runtime()
    await task_manager.stop_pubsub_listener()
    await close_pubsub_hub()
    await drain_upload_delete_tasks()
    await drain_user_s3_cleanup_tasks()
    await drain_project_cleanup_tasks()
    await drain_llm_client_close_tasks()
    await close_role_cache_redis()
    await close_ws_rate_limiter()
    await close_s3_storage()
    await cleanup_skills_storage_cache()
    await close_settings_service()
    await drain_dual_writer_event_buffer()
    shutdown_blocking_io_executor()
