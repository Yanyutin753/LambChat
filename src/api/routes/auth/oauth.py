"""
OAuth authentication routes
"""

import secrets
from inspect import isawaitable
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Path, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, StringConstraints

from src.infra.auth.turnstile import get_turnstile_service
from src.infra.logging import get_logger
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import OAuthProvider

from .utils import _get_client_ip, _get_frontend_url, _store_oauth_state, _verify_oauth_state

router = APIRouter()
logger = get_logger(__name__)


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
        raise AppError(ErrorCode.OAUTH_PROVIDER_DISABLED, args={"provider": provider})

    # 生成 state 用于 CSRF 防护
    state = secrets.token_urlsafe(32)

    # 获取客户端 IP 并存储 state
    client_ip = _get_client_ip(request)
    await _store_oauth_state(provider, state, client_ip)

    # 从请求中获取前端 URL
    frontend_url = _get_frontend_url(request)
    redirect_uri = _oauth_redirect_uri(frontend_url, provider)

    # 获取授权 URL
    auth_url = oauth_service.get_authorization_url(oauth_provider, state, redirect_uri)
    if not auth_url:
        raise AppError(ErrorCode.OAUTH_URL_FAILED)

    # 直接重定向到 OAuth 提供商授权页面（标准 OAuth 模式）
    return RedirectResponse(url=auth_url, status_code=302)


class OAuthCallbackRequest(BaseModel):
    """OAuth 回调请求"""

    code: str
    state: str


def _oauth_redirect_uri(frontend_url: str, provider: str) -> str:
    return f"{frontend_url}/api/auth/oauth/{provider}/callback"


def _frontend_callback_url(frontend_url: str) -> str:
    return f"{frontend_url}/auth/callback"


def _token_fragment(token) -> str:
    return urlencode(
        {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "expires_in": token.expires_in,
        }
    )


async def _verify_state(provider: str, state: str, client_ip: str) -> bool:
    coro_or_result = _verify_oauth_state(provider, state, client_ip)
    if isawaitable(coro_or_result):
        result = await coro_or_result
    else:
        result = coro_or_result
    return bool(result)


async def _exchange_oauth_token(
    request: Request,
    provider: str,
    code: str,
    state: str,
):
    from src.infra.auth.oauth import get_oauth_service

    oauth_service = get_oauth_service()
    oauth_provider = OAuthProvider(provider)

    frontend_url = _get_frontend_url(request)
    redirect_uri = _oauth_redirect_uri(frontend_url, provider)
    token = await oauth_service.handle_callback(oauth_provider, code, state, redirect_uri)
    return frontend_url, token


@router.post("/oauth/{provider}/callback")
async def oauth_callback(http_request: Request, provider: OAuthProviderParam):
    """
    处理 OAuth 回调

    接收授权码，交换 token。JSON 请求返回 JWT；Apple form_post 请求重定向到前端回调页。
    """
    content_type = http_request.headers.get("content-type", "").lower()
    is_form_post = "application/x-www-form-urlencoded" in content_type or (
        "multipart/form-data" in content_type
    )

    if is_form_post:
        form = await http_request.form()
        callback_request = OAuthCallbackRequest(
            code=str(form.get("code") or ""),
            state=str(form.get("state") or ""),
        )
    else:
        try:
            body = await http_request.json()
            callback_request = OAuthCallbackRequest.model_validate(body)
        except Exception as exc:
            raise AppError(ErrorCode.OAUTH_CALLBACK_INVALID) from exc

    # 验证 state 以防止 CSRF 攻击
    client_ip = _get_client_ip(http_request)
    if not await _verify_state(provider, callback_request.state, client_ip):
        logger.warning("[OAuth] Invalid state for %s from %s", provider, client_ip)
        if is_form_post:
            frontend_url = _get_frontend_url(http_request)
            error_params = urlencode({"error": "oauth_invalid_state", "provider": provider})
            return RedirectResponse(
                url=f"{frontend_url}/auth/login?{error_params}",
                status_code=302,
            )
        raise AppError(ErrorCode.OAUTH_INVALID_STATE)

    frontend_url, token = await _exchange_oauth_token(
        http_request,
        provider,
        callback_request.code,
        callback_request.state,
    )
    if not token:
        if is_form_post:
            error_params = urlencode({"error": "oauth_failed", "provider": provider})
            return RedirectResponse(
                url=f"{frontend_url}/auth/login?{error_params}",
                status_code=302,
            )
        raise AppError(ErrorCode.OAUTH_FAILED)

    if is_form_post:
        return RedirectResponse(
            url=f"{_frontend_callback_url(frontend_url)}#{_token_fragment(token)}",
            status_code=302,
        )

    return token


@router.get("/oauth/{provider}/callback")
async def oauth_callback_get(request: Request, provider: OAuthProviderParam, code: str, state: str):
    """
    处理 OAuth 回调 (GET 请求)

    接收授权码，交换 token 并重定向到前端页面。
    Token 通过 URL fragment (#) 传递，更安全且不会被服务器日志记录。
    """
    # 使用与发起 OAuth 时相同的方式获取 frontend_url，确保 redirect_uri 一致
    frontend_url = _get_frontend_url(request)

    # 验证 state 以防止 CSRF 攻击
    client_ip = _get_client_ip(request)
    if not await _verify_state(provider, state, client_ip):
        logger.warning("[OAuth] Invalid state for %s from %s", provider, client_ip)
        error_params = urlencode({"error": "oauth_invalid_state", "provider": provider})
        return RedirectResponse(url=f"{frontend_url}/auth/login?{error_params}", status_code=302)

    frontend_url, token = await _exchange_oauth_token(request, provider, code, state)

    # 构建重定向 URL 到前端的 OAuth 回调处理页面
    callback_url = _frontend_callback_url(frontend_url)

    if not token:
        # 认证失败，重定向到登录页面并显示错误
        error_params = urlencode({"error": "oauth_failed", "provider": provider})
        return RedirectResponse(url=f"{frontend_url}/auth/login?{error_params}", status_code=302)

    # 认证成功，通过 URL fragment 传递 token
    # URL fragment (# 后面的内容) 不会发送到服务器，更安全
    fragment_params = _token_fragment(token)
    return RedirectResponse(url=f"{callback_url}#{fragment_params}", status_code=302)
