"""
Utility functions for auth routes
"""

from urllib.parse import urlparse

from fastapi import Request

from src.infra.logging import get_logger

from .rate_limiter import RateLimiter

logger = get_logger(__name__)


def _get_client_ip(request: Request) -> str:
    """Get client IP address from request, handling reverse proxies.

    Checks X-Forwarded-For header first (for reverse proxy setups),
    then falls back to direct client IP.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string
    """
    # Check X-Forwarded-For header (comma-separated list, first is original client)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        ips = [ip.strip() for ip in forwarded_for.split(",")]
        if ips:
            return ips[0]

    # Fall back to direct client IP
    if request.client:
        return request.client.host

    return "unknown"


SUPPORTED_EMAIL_LANGUAGES = {"en", "zh", "ja", "ko", "ru"}


def _get_language(request: Request) -> str:
    """Extract preferred language from Accept-Language header.

    Returns a 2-letter language code (e.g. 'en', 'zh').
    Falls back to 'en' if the header is missing or unsupported.
    """
    accept_lang = request.headers.get("accept-language", "en")
    # Take the first language code before any comma or semicolon
    lang = accept_lang.split(",")[0].split("-")[0].strip().lower()
    return lang if lang in SUPPORTED_EMAIL_LANGUAGES else "en"


def _get_frontend_url(request: Request) -> str:
    """从请求中获取前端 URL

    优先使用代理透传的协议和主机信息来构造对外可见的前端 URL。
    - 开发环境：Vite 代理会设置 X-Forwarded-Host
    - 生产环境：Nginx 等代理至少应传递 Host / X-Forwarded-Proto
    """
    forwarded_host = request.headers.get("x-forwarded-host")
    host = (forwarded_host or request.headers.get("host") or "").split(",")[0].strip()
    if host:
        forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
        scheme = forwarded_proto or (
            "http" if "localhost" in host or "127.0.0.1" in host else "https"
        )
        return f"{scheme}://{host}"

    # 其次使用 Origin 请求头（适用于 AJAX 请求）
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        # 提取 origin 部分 (scheme + host + port)
        parsed = urlparse(origin)
        return f"{parsed.scheme}://{parsed.netloc}"

    # 回退到请求的 base_url
    base_url = str(request.base_url)
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def _store_oauth_state(provider: str, state: str, client_ip: str) -> None:
    """Store OAuth state in Redis for CSRF protection.

    Args:
        provider: OAuth provider name
        state: State token to store
        client_ip: Client IP address for binding
    """
    from src.infra.storage.redis import get_redis_client

    redis = get_redis_client()
    key = f"oauth:state:{provider}:{RateLimiter._safe_key_part(client_ip)}"
    # Store state with 10 minute expiry
    await redis.setex(key, 600, state)


async def _verify_oauth_state(provider: str, state: str, client_ip: str) -> bool:
    """Verify OAuth state from Redis for CSRF protection.

    Args:
        provider: OAuth provider name
        state: State token to verify
        client_ip: Client IP address for binding

    Returns:
        True if state is valid, False otherwise
    """
    from src.infra.storage.redis import get_redis_client

    redis = get_redis_client()
    key = f"oauth:state:{provider}:{RateLimiter._safe_key_part(client_ip)}"

    try:
        stored_state = await redis.get(key)
        if stored_state and stored_state == state:
            # Delete the state after successful verification (one-time use)
            await redis.delete(key)
            return True
        return False
    except Exception as e:
        logger.error("[OAuth] Failed to verify state: %s", e)
        return False
