"""
OAuth 认证服务

支持 Google、GitHub、Apple OAuth 登录。
"""

import base64
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client
from authlib.jose import JsonWebKey, jwt
from pydantic import BaseModel

from src.infra.user.storage import UserStorage
from src.kernel.config import settings
from src.kernel.schemas.user import OAuthProvider, Token, User, UserCreate

logger = logging.getLogger(__name__)

# HTTP 请求超时设置（秒）
HTTP_TIMEOUT = 10.0

# State 过期时间（秒）
STATE_EXPIRE_SECONDS = 600  # 10 minutes

# State 存储（带过期时间的内存存储）
_oauth_states: Dict[str, tuple[str, float]] = {}  # state -> (provider, expire_time)


def _cleanup_expired_states() -> None:
    """清理过期的 OAuth state"""
    current_time = time.time()
    expired_states = [
        state for state, (_, expire_time) in _oauth_states.items() if current_time > expire_time
    ]
    for state in expired_states:
        _oauth_states.pop(state, None)


class OAuthUserInfo(BaseModel):
    """OAuth 用户信息"""

    provider: OAuthProvider
    oauth_id: str
    email: str
    username: str
    avatar_url: Optional[str] = None


class OAuthService:
    """
    OAuth 服务类

    处理 OAuth 授权流程。
    """

    def __init__(self):
        self.storage = UserStorage()
        self._oauth_clients: Dict[str, AsyncOAuth2Client] = {}

    def _get_client(self, provider: OAuthProvider) -> Optional[AsyncOAuth2Client]:
        """获取 OAuth 客户端"""
        if provider.value in self._oauth_clients:
            return self._oauth_clients[provider.value]

        client_id, client_secret = self._get_client_credentials(provider)
        if not client_id or not client_secret:
            return None

        # 使用 AsyncOAuth2Client 直接创建客户端
        client = AsyncOAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
        )
        self._oauth_clients[provider.value] = client
        return client

    def _get_client_credentials(self, provider: OAuthProvider) -> tuple[str, str]:
        """获取 OAuth 客户端凭据"""
        if provider == OAuthProvider.GOOGLE:
            return settings.OAUTH_GOOGLE_CLIENT_ID, settings.OAUTH_GOOGLE_CLIENT_SECRET
        elif provider == OAuthProvider.GITHUB:
            return settings.OAUTH_GITHUB_CLIENT_ID, settings.OAUTH_GITHUB_CLIENT_SECRET
        elif provider == OAuthProvider.APPLE:
            return settings.OAUTH_APPLE_CLIENT_ID, settings.OAUTH_APPLE_CLIENT_SECRET
        return "", ""

    def _get_register_config(self, provider: OAuthProvider) -> Optional[Dict[str, Any]]:
        """获取 OAuth 注册配置"""

        if provider == OAuthProvider.GOOGLE:
            return {
                "api_base_url": "https://www.googleapis.com/oauth2/v2/",
                "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "access_token_url": "https://oauth2.googleapis.com/token",
                "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
            }
        elif provider == OAuthProvider.GITHUB:
            return {
                "api_base_url": "https://api.github.com/",
                "authorize_url": "https://github.com/login/oauth/authorize",
                "access_token_url": "https://github.com/login/oauth/access_token",
            }
        elif provider == OAuthProvider.APPLE:
            return {
                "api_base_url": "https://appleid.apple.com/",
                "authorize_url": "https://appleid.apple.com/auth/authorize",
                "access_token_url": "https://appleid.apple.com/auth/token",
            }
        return None

    def is_provider_enabled(self, provider: OAuthProvider) -> bool:
        """检查 OAuth 提供商是否启用"""
        if provider == OAuthProvider.GOOGLE:
            return bool(settings.OAUTH_GOOGLE_ENABLED)
        elif provider == OAuthProvider.GITHUB:
            return bool(settings.OAUTH_GITHUB_ENABLED)
        elif provider == OAuthProvider.APPLE:
            return bool(settings.OAUTH_APPLE_ENABLED)
        return False

    def get_authorization_url(
        self, provider: OAuthProvider, state: str, redirect_uri: str
    ) -> Optional[str]:
        """
        获取 OAuth 授权 URL

        Args:
            provider: OAuth 提供商
            state: CSRF 状态码
            redirect_uri: OAuth 回调 URL（从请求中构建）

        Returns:
            授权 URL 或 None
        """
        if not self.is_provider_enabled(provider):
            logger.warning(f"OAuth provider {provider.value} is not enabled")
            return None

        client = self._get_client(provider)
        if not client:
            logger.error(f"Failed to get OAuth client for {provider.value}")
            return None

        # 存储 state 用于后续验证（带过期时间）
        _oauth_states[state] = (provider.value, time.time() + STATE_EXPIRE_SECONDS)

        # 清理过期的 state（惰性清理）
        _cleanup_expired_states()

        try:
            if provider == OAuthProvider.GOOGLE:
                url, _ = client.create_authorization_url(
                    "https://accounts.google.com/o/oauth2/v2/auth",
                    redirect_uri=redirect_uri,
                    state=state,
                    scope="openid email profile",
                )
                return url
            elif provider == OAuthProvider.GITHUB:
                url, _ = client.create_authorization_url(
                    "https://github.com/login/oauth/authorize",
                    redirect_uri=redirect_uri,
                    state=state,
                    scope="user:email read:user",
                )
                return url
            elif provider == OAuthProvider.APPLE:
                url, _ = client.create_authorization_url(
                    "https://appleid.apple.com/auth/authorize",
                    redirect_uri=redirect_uri,
                    state=state,
                    scope="name email",
                    response_mode="form_post",
                )
                return url
        except Exception as e:
            logger.error(f"Failed to create authorization URL for {provider.value}: {e}")
            # 清理无效的 state
            _oauth_states.pop(state, None)
            return None

        return None

    async def handle_callback(
        self, provider: OAuthProvider, code: str, state: str, redirect_uri: str
    ) -> Optional[Token]:
        """
        处理 OAuth 回调

        Args:
            provider: OAuth 提供商
            code: 授权码
            state: CSRF 状态码
            redirect_uri: OAuth 回调 URL（从请求中构建）

        Returns:
            Token 或 None
        """
        # 验证 state 参数（CSRF 防护）
        stored_data = _oauth_states.pop(state, None)
        if not stored_data:
            logger.error(f"OAuth state 验证失败: state={state} 不存在")
            return None
        stored_provider, expire_time = stored_data
        if time.time() > expire_time:
            logger.error(f"OAuth state 验证失败: state={state} 已过期")
            return None
        if stored_provider != provider.value:
            logger.error(
                f"OAuth state 验证失败: 期望 provider={stored_provider}, 实际={provider.value}"
            )
            return None

        if not self.is_provider_enabled(provider):
            logger.warning(f"OAuth provider {provider.value} is not enabled")
            return None

        client = self._get_client(provider)
        if not client:
            logger.error(f"Failed to get OAuth client for {provider.value}")
            return None

        try:
            # 获取 token URL
            register_config = self._get_register_config(provider)
            token_url = register_config.get("access_token_url") if register_config else None

            # 交换 code 获取 token
            token = await client.fetch_token(
                token_url,
                code=code,
                redirect_uri=redirect_uri,
            )

            # 获取用户信息
            user_info = await self._get_user_info(provider, token)
            if not user_info:
                logger.error(f"Failed to get user info from {provider.value}")
                return None

            # 查找或创建用户
            user = await self._find_or_create_user(user_info)
            if not user:
                logger.error("Failed to find or create user")
                return None

            # 生成 JWT token
            from src.infra.auth.jwt import create_access_token, create_refresh_token

            access_token = create_access_token(user_id=user.id)
            refresh_token = create_refresh_token(user_id=user.id, username=user.username)

            return Token(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_in=settings.ACCESS_TOKEN_EXPIRE_HOURS * 3600,
            )
        except Exception as e:
            logger.error(f"Failed to handle OAuth callback for {provider.value}: {e}")
            return None

    async def _get_user_info(
        self, provider: OAuthProvider, token: Dict[str, Any]
    ) -> Optional[OAuthUserInfo]:
        """获取 OAuth 用户信息"""
        try:
            if provider == OAuthProvider.GOOGLE:
                return await self._get_google_user_info(token)
            elif provider == OAuthProvider.GITHUB:
                return await self._get_github_user_info(token)
            elif provider == OAuthProvider.APPLE:
                return await self._get_apple_user_info(token)
        except Exception as e:
            logger.error(f"Failed to get user info from {provider.value}: {e}")
        return None

    async def _get_google_user_info(self, token: Dict[str, Any]) -> Optional[OAuthUserInfo]:
        """获取 Google 用户信息"""
        access_token = token.get("access_token")
        if not access_token:
            return None

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            data = resp.json()

        return OAuthUserInfo(
            provider=OAuthProvider.GOOGLE,
            oauth_id=data["id"],
            email=data["email"],
            username=data.get("name", data["email"].split("@")[0]),
            avatar_url=data.get("picture"),
        )

    async def _get_github_user_info(self, token: Dict[str, Any]) -> Optional[OAuthUserInfo]:
        """获取 GitHub 用户信息"""
        access_token = token.get("access_token")
        if not access_token:
            return None

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # 获取用户信息
            resp = await client.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            data = resp.json()

            # 获取邮箱（如果用户没有公开邮箱）
            email = data.get("email")
            if not email:
                resp = await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                emails = resp.json()
                if emails:
                    email = emails[0].get("email")

        if not email:
            logger.error("No email found for GitHub user")
            return None

        return OAuthUserInfo(
            provider=OAuthProvider.GITHUB,
            oauth_id=str(data["id"]),
            email=email,
            username=data.get("login", email.split("@")[0]),
            avatar_url=data.get("avatar_url"),
        )

    async def _get_apple_user_info(self, token: Dict[str, Any]) -> Optional[OAuthUserInfo]:
        """
        获取 Apple 用户信息

        验证 Apple ID Token 的签名，确保令牌未被伪造。
        """
        id_token = token.get("id_token")
        if not id_token:
            logger.warning("Apple OAuth: No id_token in response")
            return None

        try:
            # 获取 Apple 公钥
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                jwks_resp = await client.get("https://appleid.apple.com/auth/keys")
                jwks_data = jwks_resp.json()

            # 解码 JWT header 获取 kid
            header_b64 = id_token.split(".")[0]
            padding = 4 - len(header_b64) % 4
            if padding != 4:
                header_b64 += "=" * padding
            header = json.loads(base64.urlsafe_b64decode(header_b64))
            kid = header.get("kid")

            # 找到匹配的公钥
            jwk = None
            for key in jwks_data.get("keys", []):
                if key.get("kid") == kid:
                    jwk = key
                    break

            if not jwk:
                logger.error(f"Apple OAuth: No matching public key found for kid={kid}")
                return None

            # 使用 authlib 验证 JWT
            public_key = JsonWebKey.import_key(jwk)
            claims = jwt.decode(
                id_token,
                public_key,
                claims_options={
                    "iss": {"essential": True, "values": ["https://appleid.apple.com"]},
                    "aud": {"essential": True, "values": [settings.OAUTH_APPLE_CLIENT_ID]},
                },
            )

            if "sub" not in claims:
                logger.warning("Apple OAuth: Missing 'sub' in id_token claims")
                return None

            return OAuthUserInfo(
                provider=OAuthProvider.APPLE,
                oauth_id=claims["sub"],
                email=claims.get("email", ""),
                username=claims.get("email", "").split("@")[0]
                if claims.get("email")
                else f"apple_{claims['sub'][:8]}",
                avatar_url=None,
            )
        except Exception as e:
            logger.error(f"Apple OAuth: Failed to verify id_token: {e}")
            return None

    async def _find_or_create_user(self, user_info: OAuthUserInfo) -> Optional[User]:
        """
        查找或创建用户（并发安全）

        使用 try-except 捕获重复用户名错误并自动重试。

        Args:
            user_info: OAuth 用户信息

        Returns:
            用户对象或 None
        """
        from src.kernel.exceptions import ValidationError

        # 尝试通过 oauth_id 查找用户
        user = await self.storage.get_by_oauth(user_info.provider.value, user_info.oauth_id)
        if user:
            return User.model_validate(user.model_dump())

        # 尝试通过邮箱查找用户（如果已存在则绑定 OAuth）
        existing_user = await self.storage.get_by_email(user_info.email)
        if existing_user:
            # 绑定 OAuth 到现有用户
            from src.kernel.schemas.user import UserUpdate

            await self.storage.update(
                existing_user.id,
                UserUpdate(
                    oauth_provider=user_info.provider,
                    oauth_id=user_info.oauth_id,
                    # 如果用户没有头像，更新头像
                    avatar_url=user_info.avatar_url or existing_user.avatar_url,
                ),
            )
            return await self.storage.get_by_id(existing_user.id)

        # 创建新用户 - 使用重试机制处理并发用户名冲突
        base_username = user_info.username
        max_retries = 10

        for attempt in range(max_retries):
            if attempt == 0:
                username = base_username
            else:
                # 添加随机后缀以避免冲突
                import random
                import string

                suffix = "".join(random.choices(string.digits, k=4))
                username = f"{base_username}_{suffix}"

            user_data = UserCreate(
                username=username,
                email=user_info.email,
                avatar_url=user_info.avatar_url,
                oauth_provider=user_info.provider,
                oauth_id=user_info.oauth_id,
            )

            try:
                user = await self.storage.create(user_data)
                return User.model_validate(user.model_dump())
            except ValidationError as e:
                # 如果是用户名冲突且还有重试机会，继续尝试
                if "用户名" in str(e) and attempt < max_retries - 1:
                    logger.debug(
                        f"Username {username} already exists, retrying... (attempt {attempt + 1})"
                    )
                    continue
                # 如果是邮箱冲突或其他错误，直接抛出
                raise

        # 不应该到达这里，但为了完整性
        logger.error(f"Failed to create user after {max_retries} attempts")
        return None


# 单例
_oauth_service: Optional[OAuthService] = None


def get_oauth_service() -> OAuthService:
    """获取 OAuth 服务单例"""
    global _oauth_service
    if _oauth_service is None:
        _oauth_service = OAuthService()
    return _oauth_service
