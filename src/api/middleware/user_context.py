"""API middleware for request processing."""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from src.infra.auth.jwt import verify_token
from src.infra.backend.context import clear_user_context, set_user_context


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
                payload = verify_token(token)
                user_id = str(payload.sub) if payload.sub else None
            except Exception:
                pass  # Token invalid, user_id stays None

        try:
            if user_id:
                set_user_context(user_id, session_id)
            response = await call_next(request)
            return response
        finally:
            clear_user_context()
