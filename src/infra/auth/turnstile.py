"""
Cloudflare Turnstile verification service
"""

import logging
from typing import Optional

import httpx

from src.kernel.config import settings

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


class TurnstileService:
    """Service for verifying Cloudflare Turnstile tokens"""

    _instance: Optional["TurnstileService"] = None

    def __init__(self) -> None:
        pass

    @classmethod
    def get_instance(cls) -> "TurnstileService":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_enabled(self) -> bool:
        """Check if Turnstile is enabled (reads fresh from settings)"""
        return settings.TURNSTILE_ENABLED and bool(settings.TURNSTILE_SECRET_KEY)

    @property
    def site_key(self) -> str:
        """Get the site key for frontend"""
        return settings.TURNSTILE_SITE_KEY

    @property
    def require_on_login(self) -> bool:
        """Check if Turnstile is required on login"""
        return settings.TURNSTILE_REQUIRE_ON_LOGIN and self.is_enabled

    @property
    def require_on_register(self) -> bool:
        """Check if Turnstile is required on registration"""
        return settings.TURNSTILE_REQUIRE_ON_REGISTER and self.is_enabled

    @property
    def require_on_password_change(self) -> bool:
        """Check if Turnstile is required on password change"""
        return settings.TURNSTILE_REQUIRE_ON_PASSWORD_CHANGE and self.is_enabled

    async def verify(self, token: Optional[str], remote_ip: Optional[str] = None) -> bool:
        """
        Verify a Turnstile token

        Args:
            token: The token from the Turnstile widget
            remote_ip: Optional client IP for additional verification

        Returns:
            True if verification succeeds, False otherwise
        """
        # Always read fresh from settings
        if not settings.TURNSTILE_ENABLED:
            logger.debug("Turnstile is not enabled, skipping verification")
            return True

        if not token:
            logger.warning("Turnstile token is missing")
            return False

        secret_key = settings.TURNSTILE_SECRET_KEY
        if not secret_key:
            logger.error("Turnstile secret key is not configured")
            return False

        try:
            async with httpx.AsyncClient() as client:
                data: dict[str, str] = {
                    "secret": secret_key,
                    "response": token,
                }
                if remote_ip:
                    data["remoteip"] = remote_ip

                response = await client.post(
                    TURNSTILE_VERIFY_URL,
                    data=data,
                    timeout=10.0,
                )
                result = response.json()

                if result.get("success"):
                    logger.debug("Turnstile verification successful")
                    return True
                else:
                    error_codes = result.get("error-codes", [])
                    logger.warning("Turnstile verification failed: %s", error_codes)
                    return False

        except httpx.TimeoutException:
            logger.error("Turnstile verification timed out")
            return False
        except Exception as e:
            logger.error("Turnstile verification error: %s", e)
            return False


def get_turnstile_service() -> TurnstileService:
    """Get the global TurnstileService instance"""
    return TurnstileService.get_instance()
