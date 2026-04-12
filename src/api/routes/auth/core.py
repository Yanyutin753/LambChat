"""
Core authentication routes (register, login, refresh, me, permissions)
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from src.api.deps import get_current_user_required
from src.infra.auth.jwt import create_access_token, create_refresh_token, decode_token
from src.infra.auth.turnstile import get_turnstile_service
from src.infra.logging import get_logger
from src.infra.user.manager import UserManager
from src.kernel.config import settings
from src.kernel.exceptions import ValidationError
from src.kernel.schemas.permission import PermissionsResponse, get_permissions_response
from src.kernel.schemas.user import (
    LoginRequest,
    RegisterResponse,
    Token,
    TokenPayload,
    User,
    UserCreate,
    UserUpdate,
)

from .utils import _get_client_ip, _get_frontend_url, _get_language

router = APIRouter()
logger = get_logger(__name__)


@router.post("/register", response_model=RegisterResponse)
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
        client_ip = _get_client_ip(request)
        if not await turnstile_service.verify(turnstile_token, client_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="人机验证失败，请重试",
            )

    manager = UserManager()
    try:
        user = await manager.register(user_data)

        # 如果要求邮箱验证，发送验证邮件
        requires_verification = settings.REQUIRE_EMAIL_VERIFICATION
        if requires_verification:
            from src.infra.email import get_email_service

            email_service = await get_email_service()
            if email_service.is_enabled():
                # 生成验证令牌（24小时有效期）
                verify_token = email_service.generate_token()
                verify_token_expires = email_service.get_token_expiry(hours=24)

                # 更新用户的验证令牌
                from src.infra.user.storage import UserStorage

                storage = UserStorage()
                await storage.update(
                    user.id,
                    UserUpdate(
                        verification_token=verify_token,
                        verification_token_expires=verify_token_expires,
                    ),
                )

                # 发送验证邮件
                frontend_url = _get_frontend_url(request)
                lang = _get_language(request)
                await email_service.send_verification_email(
                    to_email=user.email,
                    username=user.username,
                    verify_token=verify_token,
                    base_url=frontend_url,
                    lang=lang,
                )
                logger.info(
                    "[Auth] Verification email sent to %s for new user %s",
                    user.email,
                    user.username,
                )
            else:
                logger.warning("[Auth] Email verification required but email service not enabled")

        return RegisterResponse(user=user, requires_verification=requires_verification)
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
        client_ip = _get_client_ip(request)
        if not await turnstile_service.verify(turnstile_token, client_ip):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="人机验证失败，请重试",
            )

    manager = UserManager()
    try:
        token = await manager.login(credentials.username, credentials.password)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        return token
    except Exception as e:
        # 处理邮箱未验证错误
        if "EmailNotVerifiedError" in type(e).__name__ or "请先验证邮箱" in str(e):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="请先验证邮箱后再登录",
            )
        # 处理账户未激活错误
        if "AccountNotActiveError" in type(e).__name__ or "账户未激活" in str(e):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账户未激活，请验证邮箱后登录",
            )
        raise


@router.post("/refresh", response_model=Token)
async def refresh_token(request: Request):
    """刷新令牌"""
    try:
        body = await request.json()
        token = body.get("refresh_token")
        if not token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="缺少刷新令牌",
            )

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

        # 获取用户信息以验证用户仍然存在
        manager = UserManager()
        user = await manager.get_user(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在",
            )

        # 生成新的 access token 和 refresh token（轮换 refresh token）
        access_token = create_access_token(user_id=user_id)
        new_refresh_token = create_refresh_token(
            user_id=user_id,
            username=username or user.username,
        )

        return Token(
            access_token=access_token,
            refresh_token=new_refresh_token,
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
