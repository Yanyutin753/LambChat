"""API middleware for request processing."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.infra.async_utils import run_blocking_io
from src.infra.auth.jwt import verify_token
from src.infra.backend.context import clear_user_context, set_user_context
from src.infra.logging import get_logger
from src.infra.logging.context import TraceContext

logger = get_logger(__name__)


class UserContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware to set user context for each request.

    This middleware extracts user_id from JWT token and sets it in the context
    for backend operations. Context is always cleared after the request completes.
    """

    async def dispatch(self, request: Request, call_next):
        user_id = None
        session_id = request.headers.get("X-Session-Id")

        # Extract user_id from JWT token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]  # Remove "Bearer " prefix
            try:
                payload = await run_blocking_io(verify_token, token)
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
            response = await call_next(request)
            return response
        finally:
            clear_user_context()
            TraceContext.clear_request_context()
