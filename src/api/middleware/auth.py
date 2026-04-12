"""
认证中间件
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class AuthMiddleware(BaseHTTPMiddleware):
    """
    认证中间件

    验证请求中的 JWT token。
    Note: Most routes use route-level Depends(get_current_user_required) for auth.
    This middleware provides an additional layer for paths that may not have
    route-level guards.
    """

    # 不需要认证的路径（精确匹配）
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/ready",
        "/api/auth/login",
        "/api/auth/register",
        "/docs",
        "/openapi.json",
        "/api/auth/permissions",
        "/manifest.json",
        "/api/version",
    }

    # 不需要认证的路径前缀
    PUBLIC_PREFIXES = (
        "/api/auth/oauth/",
        "/api/upload/file/",
        "/assets/",
        "/icons/",
        "/favicon",
        "/static/",
    )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # CORS preflight — always pass
        if request.method == "OPTIONS":
            return await call_next(request)

        # Exact match on public paths
        if path in self.PUBLIC_PATHS:
            return await call_next(request)

        # Prefix match for known public prefixes
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # All other paths require an Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )

        return await call_next(request)
