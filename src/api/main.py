"""
FastAPI 主应用

API 入口点。
"""

import asyncio
import inspect
import warnings
from collections import OrderedDict
from contextlib import asynccontextmanager
from importlib import import_module
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.tracing import TracingMiddleware
from src.api.middleware.user_context import UserContextMiddleware
from src.api.routes import notification, share, upload
from src.api.routes.registry import register_builtin_plugin_routes, register_core_routes
from src.frontend_resolution import resolve_frontend_target
from src.infra.async_utils import run_blocking_io
from src.infra.distributed_validation import validate_distributed_runtime_settings
from src.infra.local_filesystem import ensure_local_filesystem_dirs
from src.infra.logging import get_logger, setup_logging
from src.infra.monitoring import get_memory_monitor
from src.infra.runtime_services import start_runtime_services, stop_runtime_services
from src.infra.share.seo import (
    build_public_route_seo,
    build_shared_page_error_seo,
    build_shared_page_seo,
    inject_public_route_seo_into_html,
    inject_share_seo_into_html,
)
from src.infra.task.constants import HEARTBEAT_TIMEOUT
from src.kernel.config import initialize_settings, settings
from src.kernel.extensions import PluginRuntime
from src.kernel.extensions.registry import LifecyclePhase, PluginLifecycleHookRegistration

# Suppress SyntaxWarning from oss2 SDK (invalid escape sequence in their source)
warnings.filterwarnings("ignore", message=".*invalid escape sequence.*", category=SyntaxWarning)

logger = get_logger(__name__)

STATIC_CACHE_CONTROL_BY_PREFIX = {
    "assets/": "public, max-age=31536000, immutable",
    "icons/": "public, max-age=604800",
    "images/": "public, max-age=604800, stale-while-revalidate=86400",
}
MANIFEST_CACHE_CONTROL = "public, max-age=86400"
SERVICE_WORKER_CACHE_CONTROL = "no-cache"
OFFLINE_PAGE_CACHE_CONTROL = "no-cache"
INDEX_HTML_CACHE_MAX_ENTRIES = 4
INDEX_HTML_MAX_BYTES = 2 * 1024 * 1024
_INDEX_HTML_CACHE: OrderedDict[Path, tuple[int, int, str]] = OrderedDict()
API_REQUEST_BODY_MAX_BYTES = 8 * 1024 * 1024
API_MULTIPART_UPLOAD_PATHS = {"/api/upload/file", "/api/upload/avatar", "/upload/file"}
_LIFESPAN_BACKGROUND_TASK_NAMES = (
    "session_search_backfill_task",
    "memory_monitor_startup_reset_task",
    "agent_discovery_task",
    "models_preload_task",
    "stale_task_cleanup_task",
    "stale_task_cleanup_recheck_task",
    "feishu_task",
)
_STALE_TASK_CLEANUP_RECHECK_DELAY_SECONDS = max(5.0, HEARTBEAT_TIMEOUT * 2 + 5)
PLUGIN_LIFECYCLE_HOOK_TIMEOUT_SECONDS = 5.0


def _is_body_limit_exempt(scope: Scope) -> bool:
    path = str(scope.get("path") or "")

    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    content_type = headers.get("content-type", "").lower()
    if "multipart/form-data" not in content_type:
        return False
    return (
        path in API_MULTIPART_UPLOAD_PATHS
        or path.startswith("/api/skills/upload")
        or (path.startswith("/api/skills/") and "/binary-files/" in path)
    )


class RequestBodyLimitMiddleware:
    """Reject oversized non-upload request bodies before they are materialized."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or _is_body_limit_exempt(scope):
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        content_length = headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > API_REQUEST_BODY_MAX_BYTES:
                    await self._send_too_large(scope, receive, send)
                    return
                await self.app(scope, receive, send)
                return
            except ValueError:
                pass

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                await self.app(scope, receive, send)
                return

            body.extend(message.get("body", b""))
            if len(body) > API_REQUEST_BODY_MAX_BYTES:
                await self._send_too_large(scope, receive, send)
                return

            if not message.get("more_body", False):
                break

        replayed = False

        async def replay_body() -> Message:
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay_body, send)

    async def _send_too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "Request body too large"},
        )
        await response(scope, receive, send)


def _cache_control_for_static_path(path: str) -> str | None:
    normalized_path = path.lstrip("/")
    for prefix, cache_control in STATIC_CACHE_CONTROL_BY_PREFIX.items():
        if normalized_path.startswith(prefix):
            return cache_control
    if normalized_path == "manifest.json":
        return MANIFEST_CACHE_CONTROL
    if normalized_path == "sw.js":
        return SERVICE_WORKER_CACHE_CONTROL
    if normalized_path == "offline.html":
        return OFFLINE_PAGE_CACHE_CONTROL
    return None


def _static_file_response(file_path: Path, request_path: str) -> FileResponse:
    headers = {}
    cache_control = _cache_control_for_static_path(request_path)
    if cache_control:
        headers["Cache-Control"] = cache_control
    return FileResponse(str(file_path), headers=headers)


def _is_existing_file(file_path: Path) -> bool:
    return file_path.exists() and file_path.is_file()


def _read_index_html(index_file: Path) -> str:
    stat = index_file.stat()
    if stat.st_size > INDEX_HTML_MAX_BYTES:
        raise ValueError(f"index.html too large: {stat.st_size} bytes (max {INDEX_HTML_MAX_BYTES})")
    cache_key = index_file.resolve()
    cached = _INDEX_HTML_CACHE.get(cache_key)
    if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
        _INDEX_HTML_CACHE.move_to_end(cache_key)
        return cached[2]

    html_doc = index_file.read_text(encoding="utf-8")
    _INDEX_HTML_CACHE[cache_key] = (stat.st_mtime_ns, stat.st_size, html_doc)
    while len(_INDEX_HTML_CACHE) > INDEX_HTML_CACHE_MAX_ENTRIES:
        _INDEX_HTML_CACHE.popitem(last=False)
    return html_doc


async def _warm_agent_registry() -> None:
    """Preload agent registrations without blocking startup."""
    try:
        from src.agents import discover_agents

        await run_blocking_io(discover_agents)
        logger.info("Agents discovered")
    except Exception as e:
        logger.warning("Agent discovery warm-up failed: %s", e, exc_info=True)


async def _warm_models_cache() -> None:
    """Preload model metadata without blocking application startup."""
    try:
        from src.infra.llm.models_service import refresh_models

        await refresh_models()
        logger.info("Models preloaded into memory cache")
    except Exception as e:
        logger.warning("Model cache warm-up failed: %s", e, exc_info=True)


def _schedule_models_cache_warmup(app: FastAPI) -> asyncio.Task[None]:
    """Schedule model cache warm-up and keep a task reference for shutdown."""
    task = asyncio.create_task(_warm_models_cache())
    app.state.models_preload_task = task
    return task


async def _cleanup_stale_tasks() -> None:
    """Recover stale tasks in the background after runtime listeners start."""
    try:
        from src.infra.task.manager import get_task_manager

        task_manager = get_task_manager()
        await task_manager.cleanup_stale_tasks()
        logger.info("Stale tasks cleaned up")
    except Exception as e:
        logger.warning("Stale task cleanup failed: %s", e, exc_info=True)


def _schedule_stale_task_cleanup(app: FastAPI) -> asyncio.Task[None]:
    """Schedule stale task reconciliation without blocking application readiness."""

    async def _run_recheck() -> None:
        await asyncio.sleep(_STALE_TASK_CLEANUP_RECHECK_DELAY_SECONDS)
        await _cleanup_stale_tasks()

    task = asyncio.create_task(_cleanup_stale_tasks())
    app.state.stale_task_cleanup_task = task
    app.state.stale_task_cleanup_recheck_task = asyncio.create_task(_run_recheck())
    return task


async def _cancel_background_tasks(app: FastAPI, *task_names: str) -> None:
    tasks = []
    for task_name in task_names:
        task = getattr(app.state, task_name, None)
        if task is None:
            continue
        setattr(app.state, task_name, None)
        if not task.done():
            task.cancel()
            tasks.append(task)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _stop_feishu_channels_for_shutdown(app: FastAPI) -> None:
    await _cancel_background_tasks(app, "feishu_task")
    try:
        from src.infra.channel.feishu import stop_feishu_channels

        await stop_feishu_channels()
        logger.info("Feishu channels stopped")
    except Exception as e:
        logger.warning(f"Failed to stop Feishu channels: {e}")


async def _close_route_dependency_singletons() -> None:
    from src.infra.persona_preset.manager import close_persona_preset_manager
    from src.infra.revealed_file.storage import close_revealed_file_storage

    await notification.close_notification_manager()
    from src.infra.push.manager import close_push_manager

    await close_push_manager()
    await close_revealed_file_storage()
    await upload.close_upload_route_dependencies()
    await close_persona_preset_manager()


async def _close_session_sandbox_manager_for_shutdown() -> None:
    from src.infra.sandbox.session_manager import close_session_sandbox_manager

    await close_session_sandbox_manager()


async def _cancel_lifespan_background_tasks_for_shutdown(app: FastAPI) -> None:
    await _cancel_background_tasks(app, *_LIFESPAN_BACKGROUND_TASK_NAMES)


def _startup_index_initializers():
    async def _init_agent_config_storage() -> None:
        from src.infra.agent.config_storage import get_agent_config_storage

        await get_agent_config_storage().ensure_indexes()
        logger.info("Agent config storage indexes initialized")

    async def _init_model_storage() -> None:
        from src.infra.agent.model_storage import get_model_storage

        await get_model_storage().ensure_indexes()
        logger.info("Model storage indexes initialized")

    async def _init_channel_storage() -> None:
        from src.infra.channel.channel_storage import ChannelStorage

        await ChannelStorage().ensure_indexes_if_needed()
        logger.info("Channel storage indexes initialized")

    async def _init_skill_indexes() -> None:
        from src.infra.skill import init_skill_indexes

        await init_skill_indexes()
        logger.info("Skill indexes initialized")

    async def _init_trace_storage() -> None:
        from src.infra.session.trace_storage import get_trace_storage

        await get_trace_storage().ensure_indexes_if_needed()
        logger.info("TraceStorage initialized")

    async def _init_session_storage() -> None:
        from src.infra.session.storage import SessionStorage

        await SessionStorage().ensure_indexes_if_needed()
        logger.info("SessionStorage indexes initialized")

    async def _init_revealed_file_storage() -> None:
        from src.infra.revealed_file.storage import get_revealed_file_storage

        await get_revealed_file_storage().ensure_indexes_if_needed()
        logger.info("RevealedFileStorage indexes initialized")

    async def _init_notification_storage() -> None:
        from src.infra.notification.storage import NotificationStorage

        await NotificationStorage().create_indexes()
        logger.info("NotificationStorage indexes initialized")

    async def _init_push_subscription_storage() -> None:
        from src.infra.push.storage import PushSubscriptionStorage

        await PushSubscriptionStorage().create_indexes()
        logger.info("PushSubscription indexes initialized")

    async def _init_user_storage() -> None:
        from src.infra.user.storage import UserStorage

        await UserStorage().ensure_indexes_if_needed()
        logger.info("UserStorage indexes initialized")

    async def _init_usage_storage() -> None:
        from src.infra.usage.storage import get_usage_storage

        await get_usage_storage().ensure_indexes()
        logger.info("UsageStorage indexes initialized")

    return [
        ("agent_config_storage", _init_agent_config_storage),
        ("model_storage", _init_model_storage),
        ("channel_storage", _init_channel_storage),
        ("skill_indexes", _init_skill_indexes),
        ("trace_storage", _init_trace_storage),
        ("session_storage", _init_session_storage),
        ("revealed_file_storage", _init_revealed_file_storage),
        ("notification_storage", _init_notification_storage),
        ("push_subscription_storage", _init_push_subscription_storage),
        ("user_storage", _init_user_storage),
        ("usage_storage", _init_usage_storage),
    ]


async def _initialize_startup_indexes() -> None:
    """Initialize independent storage indexes concurrently before serving traffic."""

    async def _run_initializer(name, initializer) -> None:
        try:
            await initializer()
        except Exception as e:
            logger.error("Startup index initializer failed: %s", name, exc_info=True)
            raise e

    await asyncio.gather(
        *(
            _run_initializer(name, initializer)
            for name, initializer in _startup_index_initializers()
        )
    )


async def _run_startup_indexes(app: FastAPI) -> None:
    """Initialize storage indexes before app readiness."""
    task = asyncio.create_task(_initialize_startup_indexes())
    app.state.startup_indexes_task = task
    await task
    logger.info("Startup storage indexes initialized")


async def _load_plugin_runtime_state_overrides(app: FastAPI) -> None:
    runtime = getattr(app.state, "plugin_runtime", None)
    if runtime is None:
        return
    try:
        storage = getattr(app.state, "plugin_runtime_state_storage", None)
        if storage is None:
            from src.infra.extensions import get_plugin_runtime_state_storage

            storage = get_plugin_runtime_state_storage()
            app.state.plugin_runtime_state_storage = storage
        for override in await storage.list_overrides():
            try:
                runtime.apply_stored_status(
                    override.plugin_id,
                    override.status,
                    updated_at=override.updated_at,
                    updated_by=override.updated_by,
                )
            except Exception as exc:  # noqa: BLE001 - invalid stored state is non-fatal
                logger.warning(
                    "Failed to apply plugin runtime state override for %s: %s",
                    override.plugin_id,
                    exc,
                )
        logger.info("Plugin runtime state overrides loaded")
    except Exception as exc:  # noqa: BLE001 - storage outage must not break core startup
        logger.warning("Failed to load plugin runtime state overrides: %s", exc)


async def _initialize_plugin_settings(app: FastAPI) -> None:
    runtime = getattr(app.state, "plugin_runtime", None)
    if runtime is None:
        return
    try:
        from src.infra.extensions import get_plugin_settings_service

        service = get_plugin_settings_service()
        app.state.plugin_settings_service = service
        await service.storage.ensure_indexes()
        for state in runtime.states():
            if state.manifest and state.manifest.settings:
                await service.import_legacy(state.manifest)
        logger.info("Plugin settings initialized")
    except Exception as exc:  # noqa: BLE001 - plugin settings must not block core startup
        logger.warning("Failed to initialize plugin settings: %s", exc)


def _attach_plugin_runtime_to_runtime_guards(app: FastAPI) -> None:
    runtime = getattr(app.state, "plugin_runtime", None)
    try:
        from src.infra.scheduler.runtime import get_runtime_scheduler

        get_runtime_scheduler().set_plugin_runtime(runtime)
        logger.info("Plugin runtime attached to scheduler guards")
    except Exception as exc:  # noqa: BLE001 - scheduler guard attachment is non-fatal
        logger.warning("Failed to attach plugin runtime to scheduler guards: %s", exc)
    try:
        from src.infra.tool.internal_registry import set_plugin_runtime

        set_plugin_runtime(runtime)
        logger.info("Plugin runtime attached to internal tool guards")
    except Exception as exc:  # noqa: BLE001 - tool guard attachment is non-fatal
        logger.warning("Failed to attach plugin runtime to internal tool guards: %s", exc)
    try:
        from src.agents import set_plugin_runtime as set_agent_plugin_runtime

        set_agent_plugin_runtime(runtime)
        logger.info("Plugin runtime attached to agent guards")
    except Exception as exc:  # noqa: BLE001 - agent guard attachment is non-fatal
        logger.warning("Failed to attach plugin runtime to agent guards: %s", exc)
    try:
        from src.infra.pubsub_hub import get_pubsub_hub

        get_pubsub_hub().set_plugin_runtime(runtime)
        logger.info("Plugin runtime attached to pub/sub listener guards")
    except Exception as exc:  # noqa: BLE001 - listener guard attachment is non-fatal
        logger.warning("Failed to attach plugin runtime to pub/sub listener guards: %s", exc)
    try:
        from src.infra.channel.pubsub import get_channel_config_pubsub

        get_channel_config_pubsub().set_plugin_runtime(runtime)
        logger.info("Plugin runtime attached to channel connector guards")
    except Exception as exc:  # noqa: BLE001 - channel guard attachment is non-fatal
        logger.warning("Failed to attach plugin runtime to channel connector guards: %s", exc)


def _attach_plugin_runtime_to_scheduler(app: FastAPI) -> None:
    _attach_plugin_runtime_to_runtime_guards(app)


def _resolve_plugin_lifecycle_hook(registration: PluginLifecycleHookRegistration):
    module_name, separator, callable_name = registration.module.partition(":")
    if not separator or not callable_name:
        raise ValueError(
            f"plugin lifecycle hook must use module:callable syntax: {registration.module}"
        )
    module = import_module(module_name)
    hook_callable = getattr(module, callable_name)
    if not callable(hook_callable):
        raise TypeError(f"plugin lifecycle hook is not callable: {registration.module}")
    return hook_callable


async def _invoke_plugin_lifecycle_hook(
    registration: PluginLifecycleHookRegistration,
) -> None:
    hook_callable = _resolve_plugin_lifecycle_hook(registration)
    signature = inspect.signature(hook_callable)
    required_positionals = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        }
    ]
    if required_positionals:
        result = hook_callable(registration)
    else:
        result = hook_callable()
    if inspect.isawaitable(result):
        await result


async def _run_plugin_lifecycle_hooks(app: FastAPI, phase: LifecyclePhase) -> None:
    runtime = getattr(app.state, "plugin_runtime", None)
    if not isinstance(runtime, PluginRuntime):
        return
    results = await runtime.execute_lifecycle_hooks(
        phase=phase,
        executor=_invoke_plugin_lifecycle_hook,
        timeout_seconds=PLUGIN_LIFECYCLE_HOOK_TIMEOUT_SECONDS,
    )
    if not results:
        return
    previous_results = getattr(app.state, "plugin_runtime_hook_results", [])
    app.state.plugin_runtime_hook_results = [*previous_results, *results]
    for result in results:
        log_method = logger.info if result.status == "succeeded" else logger.warning
        log_method(
            "Plugin lifecycle hook %s/%s %s in %.1fms%s",
            result.plugin_id,
            result.hook_name,
            result.status,
            result.elapsed_ms,
            f": {result.error}" if result.error else "",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    logger.info("%s v%s starting...", settings.APP_NAME, settings.APP_VERSION)

    # 初始化日志系统
    setup_logging()

    # 初始化默认角色（更新系统角色权限）
    try:
        from src.infra.role.storage import RoleStorage

        role_storage = RoleStorage()
        await role_storage.init_default_roles()
        logger.info("Default roles initialized")
    except Exception as e:
        logger.error("Failed to initialize default roles: %s", e)

    # 配置 uvicorn 访问日志格式，与项目日志完全统一
    import logging

    from src.infra.logging.filter import TraceFilter
    from src.infra.logging.formatter import ColoredFormatter

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.setLevel(logging.INFO)
    access_logger.handlers.clear()
    access_handler = logging.StreamHandler()
    # 使用项目相同的格式和 ColoredFormatter
    access_handler.setFormatter(
        ColoredFormatter(
            fmt=settings.LOG_FORMAT,
            datefmt=settings.LOG_DATE_FORMAT,
        )
    )
    # 添加 TraceFilter 以支持 trace_info
    access_handler.addFilter(TraceFilter())
    access_logger.addHandler(access_handler)

    # 从数据库初始化设置
    await initialize_settings()
    logger.info("Settings initialized from database")

    validate_distributed_runtime_settings(settings)

    # 初始化本地文件系统目录（使用数据库覆盖后的最终配置）
    ensure_local_filesystem_dirs(settings)

    # 启动进程内存监控
    memory_monitor = get_memory_monitor()
    await memory_monitor.start()
    logger.info("Memory monitor started")

    # 后台预热 Agent 注册，避免阻塞服务启动；请求路径仍有懒发现兜底
    app.state.agent_discovery_task = asyncio.create_task(_warm_agent_registry())

    await _run_startup_indexes(app)

    await _load_plugin_runtime_state_overrides(app)

    await _initialize_plugin_settings(app)

    _attach_plugin_runtime_to_runtime_guards(app)

    await _run_plugin_lifecycle_hooks(app, "startup")

    # 启动分布式运行时监听器（任务/设置/模型/记忆/WebSocket）
    await start_runtime_services()
    logger.info("Runtime distributed listeners started")

    # 后台恢复/清理残留任务；恢复逻辑自身有分布式锁与 heartbeat 判断。
    _schedule_stale_task_cleanup(app)

    # 后台预加载模型列表；请求路径仍有 memory -> Redis -> DB 懒加载兜底。
    _schedule_models_cache_warmup(app)

    # 初始化 SessionStorage 搜索索引，并异步回填历史会话
    from src.infra.session.backfill import SessionSearchBackfillWorker

    async def _backfill_session_search():
        worker = SessionSearchBackfillWorker()
        try:
            delay = getattr(settings, "SESSION_SEARCH_BACKFILL_STARTUP_DELAY_SECONDS", 30.0)
            if delay > 0:
                await asyncio.sleep(delay)
            rebuilt = await worker.run_until_complete()
            logger.info("Session search backfill finished, rebuilt %s sessions", rebuilt)
        except Exception as e:
            logger.warning("Session search backfill failed: %s", e)
        finally:
            await worker.close()
            await memory_monitor.reset_baseline()
            logger.info("Memory monitor baseline reset after session search backfill")

    _session_search_backfill_task = asyncio.create_task(_backfill_session_search())
    app.state.session_search_backfill_task = _session_search_backfill_task

    # Start Feishu channels in background (don't block app startup)
    async def _start_feishu():
        try:
            from src.kernel.extensions import FEISHU_CONNECTOR_ID, PluginUnavailableError

            runtime = getattr(app.state, "plugin_runtime", None)
            if runtime is not None:
                try:
                    runtime.ensure_channel_connector_available(FEISHU_CONNECTOR_ID)
                except PluginUnavailableError as exc:
                    logger.info("Feishu connector startup skipped by Plugin Runtime: %s", exc)
                    return

            from src.infra.channel.feishu.handler import setup_feishu_handler

            await setup_feishu_handler(
                default_agent=settings.DEFAULT_AGENT,
                show_tools=True,
            )
        except Exception as e:
            logger.warning(f"Failed to start Feishu channels: {e}")

    # Keep task reference to prevent GC from cancelling it
    _feishu_task = asyncio.create_task(_start_feishu())
    app.state.feishu_task = _feishu_task

    async def _reset_memory_monitor_after_startup() -> None:
        try:
            await memory_monitor.reset_baseline()
            logger.info("Memory monitor baseline reset after startup initialization")
        except Exception as e:
            logger.warning("Memory monitor baseline reset after startup failed: %s", e)

    app.state.memory_monitor_startup_reset_task = asyncio.create_task(
        _reset_memory_monitor_after_startup()
    )

    try:
        yield
    except asyncio.CancelledError:
        # Ctrl+C / server cancellation during lifespan shutdown is a normal exit path.
        logger.info("Application lifespan cancelled, continuing graceful shutdown")
    finally:
        # 关闭时清理
        from src.agents import AgentFactory
        from src.infra.sandbox import SandboxFactory

        await _run_plugin_lifecycle_hooks(app, "shutdown")

        # 先关闭飞书长连接并释放 lease，避免快速重启时旧锁阻止新实例启动。
        await _stop_feishu_channels_for_shutdown(app)
        # 再统一取消 lifespan 后台任务，让各任务自己的 finally 在依赖关闭前完成。
        await _cancel_lifespan_background_tasks_for_shutdown(app)

        # 停止事件合并器
        from src.infra.session.event_merger import close_event_merger
        from src.infra.session.trace_storage import close_trace_storage
        from src.infra.task.manager import get_task_manager

        await close_event_merger()
        await close_trace_storage()
        logger.info("EventMerger stopped")

        # 标记所有运行中的任务为失败
        task_manager = get_task_manager()

        # 先停止分布式运行时监听器，再关闭任务
        await stop_runtime_services()
        logger.info("Runtime distributed listeners stopped")

        from src.infra.monitoring import close_memory_monitor

        await close_memory_monitor()
        logger.info("Memory monitor stopped")

        await task_manager.shutdown()
        logger.info("Background tasks marked as failed")

        # 清理 executor 注册表
        from src.infra.task.concurrency import unregister_executor

        unregister_executor("agent_stream")
        logger.info("Executor registry cleaned up")

        # 关闭所有 sandbox
        await SandboxFactory.close_all()

        # 关闭用户级沙箱（SessionSandboxManager 管理的）
        await _close_session_sandbox_manager_for_shutdown()
        logger.info("User sandboxes stopped")

        await AgentFactory.close_all()

        await _close_route_dependency_singletons()

        # 关闭 PostgreSQL 连接池
        from src.infra.storage.checkpoint import (
            close_async_checkpointer,
            close_pg_checkpointer,
        )
        from src.infra.storage.mongodb_store import close_store
        from src.infra.storage.postgres import close_connection_pool

        await close_store()
        close_async_checkpointer()
        close_connection_pool()
        await close_pg_checkpointer()

        # 关闭 EmailService HTTP 客户端
        from src.infra.email import close_email_service

        await close_email_service()

        # 关闭 OAuth 客户端
        from src.infra.auth.oauth import close_oauth_service

        await close_oauth_service()

        # 关闭 MCP 连接池
        from src.infra.tool.mcp_pool import close_all_connections

        await close_all_connections()

        # 关闭 RateLimiter Redis 连接
        from src.api.routes.auth import close_rate_limiter

        await close_rate_limiter()

        # 关闭主 Redis 连接池
        from src.infra.storage.redis import close_redis_client

        await close_redis_client()

        # 释放 MongoDB checkpointer 引用（在关闭连接池之前）
        from src.infra.storage.checkpoint import close_mongo_checkpointer

        close_mongo_checkpointer()

        # 关闭 MongoDB 连接池
        from src.infra.storage.mongodb import close_approval_storage, close_mongo_client

        close_approval_storage()
        await close_mongo_client()

        # Cancel remaining background tasks (e.g., lark_oapi ExpiringCache cron)
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
            logger.info(f"Cancelled {len(pending)} remaining background task(s)")

        logger.info("Shutting down...")


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
    )

    # CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 自定义中间件 (顺序：后添加的先执行)
    # 执行顺序: RequestBodyLimitMiddleware -> TracingMiddleware -> AuthMiddleware -> UserContextMiddleware -> Route
    app.add_middleware(UserContextMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(TracingMiddleware)
    app.add_middleware(RequestBodyLimitMiddleware)

    register_core_routes(app)
    register_builtin_plugin_routes(app)

    # Serve frontend static files
    project_root = Path(__file__).parent.parent.parent
    frontend_target = resolve_frontend_target(
        project_root,
        settings.FRONTEND_DEV_URL if hasattr(settings, "FRONTEND_DEV_URL") else "",
    )
    if frontend_target and frontend_target[0] == "static":
        static_dir = frontend_target[1]
        assert isinstance(static_dir, Path)

        assets_dir = static_dir / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        icons_dir = static_dir / "icons"
        if icons_dir.exists():
            app.mount("/icons", StaticFiles(directory=str(icons_dir)), name="icons")

        # Serve other static files (manifest.json, etc.)
        @app.get("/manifest.json")
        async def serve_manifest():
            manifest_file = static_dir / "manifest.json"
            if await run_blocking_io(_is_existing_file, manifest_file):
                return _static_file_response(manifest_file, "manifest.json")
            return {"error": "manifest.json not found"}

        @app.get("/shared/{share_id}", response_class=HTMLResponse)
        async def serve_shared_page(share_id: str, request: Request):
            """Serve shared pages with server-injected SEO metadata."""
            index_file = static_dir / "index.html"
            if not await run_blocking_io(_is_existing_file, index_file):
                return {"error": "Frontend not built. Run 'npm run build' in frontend directory."}

            base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/") or str(
                request.base_url
            ).rstrip("/")
            html_doc = await run_blocking_io(_read_index_html, index_file)

            try:
                shared_content = await share.get_shared_content(share_id, user=None)
            except HTTPException as exc:
                reason = "auth_required" if exc.status_code == 401 else "not_found"
                seo = build_shared_page_error_seo(
                    base_url=base_url,
                    share_id=share_id,
                    app_name=settings.APP_NAME,
                    reason=reason,
                )
                rendered = inject_share_seo_into_html(html_doc, seo)
                return HTMLResponse(content=rendered, status_code=exc.status_code)

            seo = build_shared_page_seo(
                base_url=base_url,
                share_id=share_id,
                session=shared_content.session,
                owner=shared_content.owner.model_dump(),
                events=shared_content.events,
                app_name=settings.APP_NAME,
                indexable=False,
            )
            rendered = inject_share_seo_into_html(html_doc, seo)
            return HTMLResponse(content=rendered)

        # SPA fallback - serve index.html for all unmatched routes
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str, request: Request):
            """Serve SPA index.html for client-side routing."""
            # First, check if it's a static file
            static_file = static_dir / full_path
            if await run_blocking_io(_is_existing_file, static_file):
                return _static_file_response(static_file, full_path)
            # Otherwise, serve index.html for SPA routing
            index_file = static_dir / "index.html"
            if await run_blocking_io(_is_existing_file, index_file):
                base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/") or str(
                    request.base_url
                ).rstrip("/")
                path = f"/{full_path}" if full_path else "/"
                seo = build_public_route_seo(base_url=base_url, path=path)
                html_doc = await run_blocking_io(_read_index_html, index_file)
                rendered = inject_public_route_seo_into_html(html_doc, seo)
                return HTMLResponse(content=rendered)
            return {"error": "Frontend not built. Run 'npm run build' in frontend directory."}

    elif frontend_target and frontend_target[0] == "redirect":
        frontend_dev_url = frontend_target[1]
        assert isinstance(frontend_dev_url, str)

        @app.get("/{full_path:path}")
        async def serve_frontend_dev(full_path: str):
            """Redirect SPA requests to the Vite dev server during local development."""
            path = f"/{full_path}" if full_path else ""
            return RedirectResponse(url=f"{frontend_dev_url}{path}")

    return app


# 创建应用实例
app = create_app()
