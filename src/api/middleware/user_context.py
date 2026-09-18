"""API middleware for request processing."""

from starlette.requests import Request

from src.api.deps import _get_cached_user
from src.infra.auth.jwt import verify_token
from src.infra.backend.context import clear_user_context, set_user_context
from src.infra.logging import get_logger
from src.infra.logging.context import TraceContext

logger = get_logger(__name__)


class UserContextMiddleware:
    """
    Middleware to set user context for each request.

    This middleware extracts user_id from JWT token and sets it in the context
    for backend operations. Context is always cleared after the request completes.

    纯 ASGI 实现（避免基类中间件每请求的 task 与流拷贝开销）。
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        user_id = None
        session_id = request.headers.get("X-Session-Id")

        # Extract user_id from JWT token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            try:
                # verify_token 是纯 CPU 微秒级操作，无需线程池跳变；
                # 命中路由层 deps._auth_cache 时直接复用，TTL 语义不变
                payload = _get_cached_user(token)
                if payload is None:
                    payload = verify_token(token)
                request.state.auth_payload = payload
                user_id = str(payload.sub) if payload.sub else None
            except Exception as e:
                # 令牌无效/过期是常态（debug）；user_id 留 None 不阻塞请求
                logger.debug("从令牌提取 user_id 失败: %s", e)

        try:
            if user_id:
                set_user_context(user_id, session_id)
            request.state.logging_user_id = user_id
            request.state.logging_session_id = session_id
            TraceContext.set_request_context(
                request_id=getattr(request.state, "request_id", None),
                session_id=session_id,
                user_id=user_id,
                trace_id=getattr(request.state, "trace_id", None),
            )
            await self.app(scope, receive, send)
        finally:
            clear_user_context()
            TraceContext.clear_request_context()
