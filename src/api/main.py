"""
FastAPI 主应用

API 入口点。
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.tracing import TracingMiddleware
from src.api.middleware.user_context import UserContextMiddleware
from src.api.routes import (
    agent,
    auth,
    channels,
    chat,
    envvar,
    feedback,
    github,
    health,
    human,
    mcp,
    project,
    role,
    session,
    share,
    skill,
    upload,
    user,
    version,
    websocket,
)
from src.api.routes import settings as settings_router
from src.api.routes.agent import config as agent_config
from src.frontend_resolution import resolve_frontend_target
from src.infra.local_filesystem import ensure_local_filesystem_dirs
from src.infra.logging import get_logger, setup_logging
from src.kernel.config import initialize_settings, settings

logger = get_logger(__name__)


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

    # 初始化本地文件系统目录（使用数据库覆盖后的最终配置）
    ensure_local_filesystem_dirs(settings)

    # 发现并注册所有 Agent
    from src.agents import discover_agents

    discover_agents()
    logger.info("Agents discovered")

    # 初始化 Agent 配置存储索引
    from src.infra.agent.config_storage import get_agent_config_storage

    agent_config_storage = get_agent_config_storage()
    await agent_config_storage.ensure_indexes()
    logger.info("Agent config storage indexes initialized")

    # 清理残留的运行中任务（服务重启前未正常关闭的任务）
    from src.infra.task.manager import get_task_manager

    task_manager = get_task_manager()
    await task_manager.cleanup_stale_tasks()
    logger.info("Stale tasks cleaned up")

    # 启动 Redis pub/sub 监听器（支持分布式任务取消）
    await task_manager.start_pubsub_listener()
    logger.info("Task pub/sub listener started")

    # 启动 Settings pub/sub 监听器（支持分布式设置同步）
    from src.infra.settings.pubsub import get_settings_pubsub

    settings_pubsub = get_settings_pubsub()
    await settings_pubsub.start_listener()
    logger.info("Settings pub/sub listener started")

    # 启动 Memory pub/sub 监听器（支持分布式记忆缓存失效）
    from src.infra.memory.distributed import get_memory_pubsub

    memory_pubsub = get_memory_pubsub()
    await memory_pubsub.start_listener()
    logger.info("Memory pub/sub listener started")

    # 初始化内置 skills
    from src.infra.skill import init_skill_indexes

    await init_skill_indexes()

    # 初始化 TraceStorage（创建索引 + 启动事件合并器）
    from src.infra.session.trace_storage import get_trace_storage

    trace_storage = get_trace_storage()
    await trace_storage.ensure_indexes_if_needed()
    logger.info("TraceStorage initialized")

    # Start Feishu channels in background (don't block app startup)
    async def _start_feishu():
        try:
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

    try:
        yield
    except asyncio.CancelledError:
        # Ctrl+C / server cancellation during lifespan shutdown is a normal exit path.
        logger.info("Application lifespan cancelled, continuing graceful shutdown")
    finally:
        # 关闭时清理
        from src.agents import AgentFactory
        from src.infra.sandbox import SandboxFactory

        # 停止事件合并器
        from src.infra.session.event_merger import get_event_merger
        from src.infra.task.manager import get_task_manager

        merger = get_event_merger(None)
        await merger.stop()
        logger.info("EventMerger stopped")

        # 标记所有运行中的任务为失败
        task_manager = get_task_manager()

        # 先停止 pub/sub 监听器，再关闭任务
        await task_manager.stop_pubsub_listener()
        logger.info("Task pub/sub listener stopped")

        # 停止 Settings pub/sub 监听器
        from src.infra.settings.pubsub import get_settings_pubsub

        settings_pubsub = get_settings_pubsub()
        await settings_pubsub.stop_listener()
        logger.info("Settings pub/sub listener stopped")

        # 停止 Memory pub/sub 监听器 + 关闭 memory backend
        from src.infra.memory.distributed import get_memory_pubsub
        from src.infra.memory.tools import shutdown as memory_shutdown

        memory_pubsub = get_memory_pubsub()
        await memory_pubsub.stop_listener()
        await memory_shutdown()
        logger.info("Memory pub/sub listener stopped, backend closed")

        await task_manager.shutdown()
        logger.info("Background tasks marked as failed")

        # 清理 executor 注册表
        from src.infra.task.concurrency import unregister_executor

        unregister_executor("agent_stream")
        logger.info("Executor registry cleaned up")

        # 关闭所有 sandbox
        await SandboxFactory.close_all()

        # 关闭用户级沙箱（SessionSandboxManager 管理的）
        from src.infra.sandbox.session_manager import get_session_sandbox_manager

        sandbox_manager = get_session_sandbox_manager()
        await sandbox_manager.close_all()
        logger.info("User sandboxes stopped")

        await AgentFactory.close_all()

        # 关闭 PostgreSQL 连接池
        from src.infra.storage.postgres import close_connection_pool

        close_connection_pool()

        # 关闭 EmailService HTTP 客户端
        from src.infra.email import get_email_service

        email_service = await get_email_service()
        await email_service.close()

        # 关闭 RateLimiter Redis 连接
        from src.api.routes.auth import get_rate_limiter

        rate_limiter = get_rate_limiter()
        await rate_limiter.close()

        # 关闭主 Redis 连接池
        from src.infra.storage.redis import close_redis_client

        await close_redis_client()

        # 关闭 MongoDB 连接池
        from src.infra.storage.mongodb import close_mongo_client

        await close_mongo_client()

        # 关闭 Feishu 渠道
        try:
            from src.infra.channel.feishu import stop_feishu_channels

            await stop_feishu_channels()
            logger.info("Feishu channels stopped")
        except Exception as e:
            logger.warning(f"Failed to stop Feishu channels: {e}")

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
    # 执行顺序: TracingMiddleware -> AuthMiddleware -> UserContextMiddleware -> Route
    app.add_middleware(UserContextMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(TracingMiddleware)

    # 注册路由
    app.include_router(health.router, tags=["Health"])
    app.include_router(version.router, prefix="/api", tags=["Version"])
    # Chat 路由: /api/chat/stream 后台执行, /api/chat/sessions/{id}/stream SSE
    app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
    # Agent 路由: /api/agents 列表, /api/{agent_id}/stream 和 /api/{agent_id}/chat
    app.include_router(agent.router, prefix="/api", tags=["Agents"])
    # Agent 配置路由: /api/agent/config 全局配置和用户偏好
    app.include_router(agent_config.router, prefix="/api/agent/config", tags=["Agent Config"])
    app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
    app.include_router(user.router, prefix="/api/users", tags=["Users"])
    app.include_router(role.router, prefix="/api/roles", tags=["Roles"])
    app.include_router(session.router, prefix="/api/sessions", tags=["Sessions"])
    app.include_router(project.router, prefix="/api/projects", tags=["Projects"])
    app.include_router(share.router, prefix="/api/share", tags=["Share"])
    app.include_router(skill.router, prefix="/api/skills", tags=["Skills"])
    app.include_router(github.router, prefix="/api/github", tags=["GitHub"])

    # User marketplace API
    from src.api.routes.marketplace import router as marketplace_router

    app.include_router(marketplace_router, prefix="/api/marketplace", tags=["Marketplace"])

    app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
    app.include_router(mcp.router, prefix="/api/mcp", tags=["MCP"])
    app.include_router(mcp.admin_router, prefix="/api/admin/mcp", tags=["MCP Admin"])
    app.include_router(envvar.router, prefix="/api/env-vars", tags=["Environment Variables"])
    app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
    app.include_router(human.router, prefix="/human", tags=["Human"])
    app.include_router(feedback.router, prefix="/api/feedback", tags=["Feedback"])
    # Generic channel configuration
    app.include_router(channels.router, prefix="/api/channels", tags=["Channels"])
    # WebSocket 路由: /ws 用于实时通知
    app.include_router(websocket.router, tags=["WebSocket"])

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
            if manifest_file.exists():
                return FileResponse(str(manifest_file))
            return {"error": "manifest.json not found"}

        # SPA fallback - serve index.html for all unmatched routes
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            """Serve SPA index.html for client-side routing."""
            # First, check if it's a static file
            static_file = static_dir / full_path
            if static_file.exists() and static_file.is_file():
                return FileResponse(str(static_file))
            # Otherwise, serve index.html for SPA routing
            index_file = static_dir / "index.html"
            if index_file.exists():
                return FileResponse(str(index_file))
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
