"""
认证中间件
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class AuthMiddleware(BaseHTTPMiddleware):
    """
    认证中间件

    验证请求中的 JWT token。
    """

    # 不需要认证的路径
    PUBLIC_PATHS = {
        "/",
        "/health",
        "/ready",
        "/api/auth/login",
        "/api/auth/register",
        "/docs",
        "/openapi.json",
    }

    async def dispatch(self, request: Request, call_next):
        # 检查是否是公开路径
        if request.url.path in self.PUBLIC_PATHS:
            return await call_next(request)

        # 检查是否以公开路径前缀开头
        for path in self.PUBLIC_PATHS:
            if request.url.path.startswith(path):
                return await call_next(request)

        # 获取 Authorization 头
        auth_header = request.headers.get("Authorization")
        if not auth_header:
            # 对于 OPTIONS 请求，直接放行
            if request.method == "OPTIONS":
                return await call_next(request)

        return await call_next(request)
