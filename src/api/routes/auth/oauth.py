"""
OAuth authentication routes
"""

import logging
import secrets
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Path, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, StringConstraints

from src.infra.auth.turnstile import get_turnstile_service
from src.kernel.config import settings
from src.kernel.schemas.user import OAuthProvider

from .utils import _get_client_ip, _get_frontend_url, _store_oauth_state, _verify_oauth_state

router = APIRouter()
logger = logging.getLogger(__name__)


# OAuth provider path parameter with validation
OAuthProviderParam = Annotated[
    str,
    StringConstraints(pattern="^(google|github|apple)$"),
    Path(description="OAuth provider name", examples=["google", "github", "apple"]),
]


@router.get("/oauth/providers")
async def get_oauth_providers():
    """
    获取可用的 OAuth 提供商列表和认证设置

    返回已启用的 OAuth 登录选项以及注册是否启用。
    """
    providers: list[dict[str, str]] = []
    try:
        from src.infra.auth.oauth import get_oauth_service

        oauth_service = get_oauth_service()
        for provider in OAuthProvider:
            if oauth_service.is_provider_enabled(provider):
                providers.append(
                    {
                        "id": provider.value,
                        "name": provider.value.capitalize(),
                    }
                )
    except Exception as e:
        logger.error("OAuth providers error: %s", e, exc_info=True)

    # 获取 Turnstile 配置
    turnstile_service = get_turnstile_service()

    return {
        "providers": providers,
        "registration_enabled": settings.ENABLE_REGISTRATION,
        "turnstile": {
            "enabled": turnstile_service.is_enabled,
            "site_key": turnstile_service.site_key,
            "require_on_login": turnstile_service.require_on_login,
            "require_on_register": turnstile_service.require_on_register,
            "require_on_password_change": turnstile_service.require_on_password_change,
        },
    }


@router.get("/oauth/{provider}")
async def oauth_login(request: Request, provider: OAuthProviderParam):
    """
    发起 OAuth 授权

    返回授权 URL，前端应重定向到该 URL。
    """
    from src.infra.auth.oauth import get_oauth_service

    oauth_service = get_oauth_service()
    oauth_provider = OAuthProvider(provider)

    if not oauth_service.is_provider_enabled(oauth_provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth provider '{provider}' is not enabled",
        )

    # 生成 state 用于 CSRF 防护
    state = secrets.token_urlsafe(32)

    # 获取客户端 IP 并存储 state
    client_ip = _get_client_ip(request)
    await _store_oauth_state(provider, state, client_ip)

    # 从请求中获取前端 URL
    frontend_url = _get_frontend_url(request)
    redirect_uri = f"{frontend_url}/api/auth/oauth/{provider}/callback"

    # 获取授权 URL
    auth_url = oauth_service.get_authorization_url(oauth_provider, state, redirect_uri)
    if not auth_url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create authorization URL",
        )

    # 返回授权 URL 和 state
    return {"authorization_url": auth_url, "state": state}


class OAuthCallbackRequest(BaseModel):
    """OAuth 回调请求"""

    code: str
    state: str


@router.post("/oauth/{provider}/callback")
async def oauth_callback(
    http_request: Request, provider: OAuthProviderParam, request: OAuthCallbackRequest
):
    """
    处理 OAuth 回调

    接收授权码，交换 token 并返回 JWT。
    """
    from src.infra.auth.oauth import get_oauth_service

    oauth_service = get_oauth_service()
    oauth_provider = OAuthProvider(provider)

    # 验证 state 以防止 CSRF 攻击
    client_ip = _get_client_ip(http_request)
    if not await _verify_oauth_state(provider, request.state, client_ip):
        logger.warning("[OAuth] Invalid state for %s from %s", provider, client_ip)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state. Please try logging in again.",
        )

    # 使用与发起 OAuth 时相同的方式获取 frontend_url，确保 redirect_uri 一致
    frontend_url = _get_frontend_url(http_request)
    redirect_uri = f"{frontend_url}/api/auth/oauth/{provider}/callback"

    token = await oauth_service.handle_callback(
        oauth_provider, request.code, request.state, redirect_uri
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OAuth authentication failed",
        )

    return token


@router.get("/oauth/{provider}/callback")
async def oauth_callback_get(request: Request, provider: OAuthProviderParam, code: str, state: str):
    """
    处理 OAuth 回调 (GET 请求)

    接收授权码，交换 token 并重定向到前端页面。
    Token 通过 URL fragment (#) 传递，更安全且不会被服务器日志记录。
    """
    from src.infra.auth.oauth import get_oauth_service

    oauth_service = get_oauth_service()
    oauth_provider = OAuthProvider(provider)

    # 使用与发起 OAuth 时相同的方式获取 frontend_url，确保 redirect_uri 一致
    frontend_url = _get_frontend_url(request)
    redirect_uri = f"{frontend_url}/api/auth/oauth/{provider}/callback"

    # 验证 state 以防止 CSRF 攻击
    client_ip = _get_client_ip(request)
    if not await _verify_oauth_state(provider, state, client_ip):
        logger.warning("[OAuth] Invalid state for %s from %s", provider, client_ip)
        error_params = urlencode({"error": "invalid_state", "provider": provider})
        return RedirectResponse(url=f"{frontend_url}/login?{error_params}", status_code=302)

    token = await oauth_service.handle_callback(oauth_provider, code, state, redirect_uri)

    # 构建重定向 URL 到前端的 OAuth 回调处理页面
    callback_url = f"{frontend_url}/auth/callback"

    if not token:
        # 认证失败，重定向到登录页面并显示错误
        error_params = urlencode({"error": "oauth_failed", "provider": provider})
        return RedirectResponse(url=f"{frontend_url}/login?{error_params}", status_code=302)

    # 认证成功，通过 URL fragment 传递 token
    # URL fragment (# 后面的内容) 不会发送到服务器，更安全
    fragment_params = urlencode(
        {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_in": token.expires_in,
        }
    )
    return RedirectResponse(url=f"{callback_url}#{fragment_params}", status_code=302)
