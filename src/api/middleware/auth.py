"""
认证中间件
"""

from fastapi import Request
from fastapi.responses import JSONResponse

from src.kernel.config import settings


class AuthMiddleware:
    """
    认证中间件

    验证请求中的 JWT token。
    Note: Most routes use route-level Depends(get_current_user_required) for auth.
    This middleware provides an additional layer for paths that may not have
    route-level guards.

    纯 ASGI 实现（避免基类中间件每请求的 task 与流拷贝开销）。
    """

    def __init__(self, app) -> None:
        self.app = app

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
        "/api/push/vapid-public-key",
        "/manifest.json",
        "/sw.js",
        "/offline.html",
        "/api/version",
        "/robots.txt",
        "/install.sh",
        "/sitemap.xml",
        "/index.html",
    }

    # 不需要认证的路径前缀
    PUBLIC_PREFIXES = (
        "/api/auth/oauth/",
        "/api/auth/refresh",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/auth/verify-email",
        "/api/auth/resend-verification",
        "/api/upload/file/",  # 文件访问端点 - 设计为公开以支持文件分享和前端访问
        # release 资产下载代理：与 /api/version 同为公开端点（移动端更新链路）。
        # 必须挂前缀列表——PUBLIC_PATHS 是精确匹配集合，挡不住
        # /api/version/assets/<name>/download 实际路径（2026-09-07 生产 401 事故）。
        "/api/version/assets/",
        "/assets/",
        "/icons/",
        "/images/",
        "/fonts/",
        "/shared/",
        "/api/share/public/",
        "/api/agents",
        "/auth/",
        "/favicon",
        "/static/",
    )

    @staticmethod
    def _is_browser_page_request(request: Request) -> bool:
        """
        Allow unauthenticated browser navigations for SPA routes.

        API/XHR requests usually send ``Accept: application/json`` or ``*/*``,
        while full page navigations include ``text/html``. This keeps backend
        APIs protected and lets the frontend router handle routes like
        ``/models`` after the request reaches the SPA fallback.
        """
        if request.method not in {"GET", "HEAD"}:
            return False

        accept = request.headers.get("accept", "")
        return "text/html" in accept.lower()

    @staticmethod
    def _cors_response(request: Request, status_code: int, content: dict) -> JSONResponse:
        """Build a JSONResponse with CORS headers so browsers don't block it.

        Only echoes the Origin when it is in the allowlist — never reflects
        arbitrary origins, since this response carries credential headers.
        """
        origin = request.headers.get("origin", "")
        response = JSONResponse(status_code=status_code, content=content)
        allowed = getattr(settings, "ALLOWED_ORIGINS", []) or []
        if origin and origin in allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
        return response

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        path = request.url.path

        async def _call_next() -> None:
            await self.app(scope, receive, send)

        # CORS preflight — always pass
        if request.method == "OPTIONS":
            await _call_next()
            return

        # Exact match on public paths
        if path in self.PUBLIC_PATHS:
            await _call_next()
            return

        # Prefix match for known public prefixes
        for prefix in self.PUBLIC_PREFIXES:
            if path.startswith(prefix):
                await _call_next()
                return

        # Let browser page navigations reach the SPA fallback / redirect route.
        if self._is_browser_page_request(request):
            await _call_next()
            return

        # All other paths require an Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            # 统一错误契约 {"detail": {code, message}}（JSONResponse 直接以 ASGI 协议写出）
            response = self._cors_response(
                request,
                status_code=401,
                content={
                    "detail": {
                        "code": "unauthorized",
                        "message": "Authentication credentials not provided",
                    }
                },
            )
            await response(scope, receive, send)
            return

        await _call_next()
