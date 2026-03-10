"""
认证路由
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, StringConstraints

from src.api.deps import get_current_user_required
from src.infra.auth.jwt import create_access_token, decode_token
from src.infra.auth.password import verify_password
from src.infra.auth.turnstile import get_turnstile_service
from src.infra.user.manager import UserManager
from src.kernel.config import settings
from src.kernel.exceptions import ValidationError
from src.kernel.schemas.permission import PermissionsResponse, get_permissions_response
from src.kernel.schemas.user import LoginRequest, Token, TokenPayload, User, UserCreate

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)


@router.post("/register", response_model=User)
async def register(user_data: UserCreate, request: Request):
    """用户注册"""
    # 检查是否允许注册
    if not settings.ENABLE_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="注册已关闭",
        )

    # Turnstile 验证
    turnstile_service = get_turnstile_service()
    if turnstile_service.require_on_register:
        turnstile_token = request.headers.get("X-Turnstile-Token")
        client_ip = request.client.host if request.client else None
        if not await turnstile_service.verify(turnstile_token, client_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="人机验证失败，请重试",
            )

    manager = UserManager()
    try:
        user = await manager.register(user_data)
        return user
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/login", response_model=Token)
async def login(credentials: LoginRequest, request: Request):
    """用户登录"""
    # Turnstile 验证
    turnstile_service = get_turnstile_service()
    if turnstile_service.require_on_login:
        turnstile_token = request.headers.get("X-Turnstile-Token")
        client_ip = request.client.host if request.client else None
        if not await turnstile_service.verify(turnstile_token, client_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="人机验证失败，请重试",
            )

    manager = UserManager()
    token = await manager.login(credentials.username, credentials.password)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    return token


@router.post("/refresh", response_model=Token)
async def refresh_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """刷新令牌"""
    try:
        token = credentials.credentials
        payload = decode_token(token)

        # 验证是否是 refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的刷新令牌",
            )

        user_id = payload.get("sub")
        username = payload.get("username")

        if not user_id or not username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的令牌内容",
            )

        # 获取用户信息以获取角色和权限
        manager = UserManager()
        user = await manager.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在",
            )

        # 获取角色和权限
        from src.infra.role.storage import RoleStorage

        role_storage = RoleStorage()
        roles = []
        permissions = set()

        for role_name in user.roles:
            role = await role_storage.get_by_name(role_name)
            if role:
                roles.append(role.name)
                for perm in role.permissions:
                    permissions.add(perm.value)

        # 生成新的 access token（用户信息从 API 动态获取）
        access_token = create_access_token(user_id=user_id)

        return Token(
            access_token=access_token,
            refresh_token=token,  # 保持原来的 refresh token
            expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"无效的刷新令牌: {str(e)}",
        )


@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """获取当前用户信息（包含动态权限）"""
    manager = UserManager()
    user = await manager.get_user(current_user.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    # 使用 TokenPayload 中已经动态获取的权限
    user.permissions = current_user.permissions
    return user


@router.get("/permissions", response_model=PermissionsResponse)
async def get_permissions():
    """
    获取所有可用权限列表

    返回按分组的权限列表，用于前端动态渲染权限选择器。
    此接口无需认证即可访问。
    """
    return get_permissions_response()


# ============================================
# User Profile Endpoints
# ============================================


class PasswordChangeRequest(BaseModel):
    """Request schema for changing password"""

    old_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    request: PasswordChangeRequest,
    http_request: Request,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """
    修改当前用户密码

    需要提供旧密码和新密码。
    """
    # Turnstile 验证
    turnstile_service = get_turnstile_service()
    if turnstile_service.require_on_password_change:
        turnstile_token = http_request.headers.get("X-Turnstile-Token")
        client_ip = http_request.client.host if http_request.client else None
        if not await turnstile_service.verify(turnstile_token, client_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="人机验证失败，请重试",
            )

    manager = UserManager()
    user = await manager.get_user(current_user.sub)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # Verify old password
    from src.infra.user.storage import UserStorage

    storage = UserStorage()
    db_user = await storage.get_by_id(current_user.sub)

    if not db_user or not verify_password(request.old_password, db_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="旧密码错误",
        )

    # Update password
    from src.kernel.schemas.user import UserUpdate

    await storage.update(current_user.sub, UserUpdate(password=request.new_password))

    return {"message": "密码修改成功"}


class AvatarUpdateRequest(BaseModel):
    """Request schema for updating avatar"""

    avatar_url: str


class UsernameUpdateRequest(BaseModel):
    """Request schema for updating username"""

    username: str = Field(..., min_length=3, max_length=50)


@router.post("/update-avatar")
async def update_avatar(
    request: AvatarUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新当前用户头像

    需要提供头像 URL（S3 上传后返回的 URL）。
    """
    manager = UserManager()
    user = await manager.get_user(current_user.sub)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    # Update avatar_url
    from src.infra.user.storage import UserStorage
    from src.kernel.schemas.user import UserUpdate

    storage = UserStorage()
    updated_user = await storage.update(current_user.sub, UserUpdate(avatar_url=request.avatar_url))

    return updated_user


@router.get("/profile", response_model=User)
async def get_user_profile(
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """
    获取当前用户个人资料

    返回用户的完整信息，包括头像 URL 等。
    """
    manager = UserManager()
    user = await manager.get_user(current_user.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return user


@router.post("/update-username")
async def update_username(
    request: UsernameUpdateRequest,
    current_user: TokenPayload = Depends(get_current_user_required),
):
    """
    更新当前用户名

    用户名不能与现有用户名重复。
    """
    from src.infra.user.storage import UserStorage
    from src.kernel.schemas.user import UserUpdate

    storage = UserStorage()
    try:
        updated_user = await storage.update(current_user.sub, UserUpdate(username=request.username))
        return updated_user
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


# ============================================
# OAuth Endpoints
# ============================================

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
        from src.kernel.schemas.user import OAuthProvider

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


def _get_frontend_url(request: Request) -> str:
    """从请求中获取前端 URL

    通过 X-Forwarded-Host 头自动检测前端 URL，无需手动配置。
    - 开发环境：Vite 代理会自动设置 X-Forwarded-Host
    - 生产环境：Nginx 等代理需配置传递 X-Forwarded-Host
    """
    from urllib.parse import urlparse

    # 检查代理转发的原始 Host（Vite 代理会设置 X-Forwarded-Host）
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_host:
        # 使用 X-Forwarded-Host 构建 URL
        # 默认使用 https，除非是 localhost
        scheme = (
            "http" if "localhost" in forwarded_host or "127.0.0.1" in forwarded_host else "https"
        )
        return f"{scheme}://{forwarded_host}"

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


@router.get("/oauth/{provider}")
async def oauth_login(request: Request, provider: OAuthProviderParam):
    """
    发起 OAuth 授权

    返回授权 URL，前端应重定向到该 URL。
    """
    import secrets

    from src.infra.auth.oauth import get_oauth_service
    from src.kernel.schemas.user import OAuthProvider

    oauth_service = get_oauth_service()
    oauth_provider = OAuthProvider(provider)

    if not oauth_service.is_provider_enabled(oauth_provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"OAuth provider '{provider}' is not enabled",
        )

    # 生成 state 用于 CSRF 防护
    state = secrets.token_urlsafe(32)

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
    from src.kernel.schemas.user import OAuthProvider

    oauth_service = get_oauth_service()
    oauth_provider = OAuthProvider(provider)

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
    from urllib.parse import urlencode

    from fastapi.responses import RedirectResponse

    from src.infra.auth.oauth import get_oauth_service
    from src.kernel.schemas.user import OAuthProvider

    oauth_service = get_oauth_service()
    oauth_provider = OAuthProvider(provider)

    # 使用与发起 OAuth 时相同的方式获取 frontend_url，确保 redirect_uri 一致
    frontend_url = _get_frontend_url(request)
    redirect_uri = f"{frontend_url}/api/auth/oauth/{provider}/callback"

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
