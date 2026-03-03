"""
FastAPI 主应用

API 入口点。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.middleware.auth import AuthMiddleware
from src.api.middleware.tracing import TracingMiddleware
from src.api.middleware.user_context import UserContextMiddleware
from src.api.routes import (
    agent,
    auth,
    chat,
    health,
    human,
    mcp,
    role,
    session,
    share,
    skill,
    upload,
    user,
    version,
)
from src.api.routes import settings as settings_router
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

    # 发现并注册所有 Agent
    from src.agents import discover_agents

    discover_agents()
    logger.info("Agents discovered")

    # 初始化默认角色
    from src.infra.role.manager import RoleManager

    role_manager = RoleManager()
    await role_manager.init_default_roles()
    logger.info("Default roles initialized")

    # 清理残留的运行中任务（服务重启前未正常关闭的任务）
    from src.infra.task.manager import get_task_manager

    task_manager = get_task_manager()
    await task_manager.cleanup_stale_tasks()
    logger.info("Stale tasks cleaned up")

    yield

    # 关闭时清理
    from src.agents import AgentFactory
    from src.infra.sandbox import SandboxFactory
    from src.infra.task.manager import get_task_manager

    # 标记所有运行中的任务为失败
    task_manager = get_task_manager()
    await task_manager.shutdown()
    logger.info("Background tasks marked as failed")

    # 关闭所有 sandbox
    await SandboxFactory.close_all()

    await AgentFactory.close_all()

    # 关闭 PostgreSQL 连接池
    from src.infra.storage.postgres import close_connection_pool

    close_connection_pool()
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
    app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
    app.include_router(user.router, prefix="/api/users", tags=["Users"])
    app.include_router(role.router, prefix="/api/roles", tags=["Roles"])
    app.include_router(session.router, prefix="/api/sessions", tags=["Sessions"])
    app.include_router(share.router, prefix="/api/share", tags=["Share"])
    app.include_router(skill.router, prefix="/api/skills", tags=["Skills"])
    app.include_router(skill.admin_router, prefix="/api/admin/skills", tags=["Skills Admin"])
    app.include_router(settings_router.router, prefix="/api/settings", tags=["Settings"])
    app.include_router(mcp.router, prefix="/api/mcp", tags=["MCP"])
    app.include_router(mcp.admin_router, prefix="/api/admin/mcp", tags=["MCP Admin"])
    app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
    app.include_router(human.router, prefix="/human", tags=["Human"])

    # Serve frontend static files
    static_dir = Path(__file__).parent.parent.parent / "static"
    if static_dir.exists():
        # Mount entire static directory for all static files
        app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")
        app.mount("/icons", StaticFiles(directory=str(static_dir / "icons")), name="icons")

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

    return app


# 创建应用实例
app = create_app()
