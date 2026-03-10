"""Resend email service implementation."""

from __future__ import annotations

import json
import logging
import secrets
import threading
from datetime import datetime, timedelta, timezone
from email.utils import formataddr
from typing import Optional

import resend  # type: ignore

from src.kernel.config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Email service using Resend API.

    Provides email functionality for:
    - Password reset
    - Email verification
    - Welcome emails

    Supports multiple accounts with round-robin rotation.
    Each account can have its own API key and sender address.
    """

    _instance: Optional[EmailService] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        """Initialize the email service."""
        self._enabled = settings.EMAIL_ENABLED
        self._accounts = self._parse_accounts()
        self._current_index = 0
        self._reset_expire_hours = settings.PASSWORD_RESET_EXPIRE_HOURS

        if self._enabled and self._accounts:
            logger.info(
                "[EmailService] Initialized with %d Resend account(s)",
                len(self._accounts),
            )
        elif self._enabled:
            logger.warning("[EmailService] Email enabled but no accounts configured")
        else:
            logger.info("[EmailService] Email service disabled")

    def _parse_accounts(self) -> list[dict[str, str]]:
        """Parse account configurations.

        Priority:
        1. RESEND_ACCOUNTS JSON array
        2. Fallback to single RESEND_API_KEY + EMAIL_FROM + EMAIL_FROM_NAME

        Returns:
            List of account dicts with api_key, email_from, email_from_name.
        """
        accounts: list[dict[str, str]] = []

        # Priority 1: Parse JSON accounts config
        resend_accounts = settings.RESEND_ACCOUNTS
        if resend_accounts:
            try:
                if isinstance(resend_accounts, str):
                    resend_accounts = json.loads(resend_accounts)

                if isinstance(resend_accounts, list):
                    for acc in resend_accounts:
                        if isinstance(acc, dict) and acc.get("api_key"):
                            accounts.append(
                                {
                                    "api_key": str(acc.get("api_key", "")),
                                    "email_from": str(acc.get("email_from", settings.EMAIL_FROM)),
                                    "email_from_name": str(
                                        acc.get(
                                            "email_from_name",
                                            settings.EMAIL_FROM_NAME,
                                        )
                                    ),
                                }
                            )
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("[EmailService] Failed to parse RESEND_ACCOUNTS: %s", e)

        # Priority 2: Fallback to single key config (backward compatible)
        if not accounts and settings.RESEND_API_KEY:
            # Support comma-separated keys with same email_from
            keys = [k.strip() for k in settings.RESEND_API_KEY.split(",") if k.strip()]
            for key in keys:
                accounts.append(
                    {
                        "api_key": key,
                        "email_from": settings.EMAIL_FROM,
                        "email_from_name": settings.EMAIL_FROM_NAME,
                    }
                )

        return accounts

    def _mask_api_key(self, key: str) -> str:
        """Mask API key for safe logging.

        Args:
            key: API key to mask.

        Returns:
            Masked key showing only first/last 4 characters.
        """
        if not key or len(key) < 8:
            return "***"
        return key[:4] + "..." + key[-4:]

    def _get_next_account(self) -> Optional[dict[str, str]]:
        """Get next account using round-robin rotation.

        Thread-safe rotation through available accounts.

        Returns:
            Account dict or None if no accounts configured.
        """
        if not self._accounts:
            return None

        with EmailService._lock:
            account = self._accounts[self._current_index]
            self._current_index = (self._current_index + 1) % len(self._accounts)
            return account.copy()

    @classmethod
    def get_instance(cls) -> EmailService:
        """Get singleton instance of EmailService."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_enabled(self) -> bool:
        """Check if email service is enabled and configured."""
        return self._enabled and bool(self._accounts)

    def _get_from_address(self, account: dict[str, str]) -> str:
        """Get formatted sender address from account.

        Args:
            account: Account dict with email_from and email_from_name.

        Returns:
            Formatted sender address.
        """
        return formataddr((account.get("email_from_name", ""), account.get("email_from", "")))

    def generate_token(self) -> str:
        """Generate a secure random token for password reset or email verification."""
        return secrets.token_urlsafe(32)

    def get_token_expiry(self, hours: Optional[int] = None) -> datetime:
        """Get token expiry datetime.

        Args:
            hours: Number of hours until expiry. Defaults to
                PASSWORD_RESET_EXPIRE_HOURS.

        Returns:
            Datetime when token expires.
        """
        if hours is None:
            hours = self._reset_expire_hours
        return datetime.now(timezone.utc) + timedelta(hours=hours)

    async def send_password_reset_email(
        self, to_email: str, username: str, reset_token: str, base_url: str
    ) -> bool:
        """Send password reset email.

        Args:
            to_email: Recipient email address.
            username: User's username for personalization.
            reset_token: Password reset token.
            base_url: Base URL for constructing reset link.

        Returns:
            True if email sent successfully, False otherwise.
        """
        if not self.is_enabled():
            logger.warning("[EmailService] Cannot send email: service not enabled")
            return False

        account = self._get_next_account()
        if not account:
            logger.warning("[EmailService] No accounts available")
            return False

        resend.api_key = account["api_key"]
        reset_url = base_url.rstrip("/") + "/reset-password?token=" + reset_token
        from_name = account.get("email_from_name", "LambChat")

        subject = from_name + " - 重置密码 / Password Reset"
        expire_hours = str(self._reset_expire_hours)

        html_content = (
            """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0; padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">🔐 """
            + from_name
            + """</h1>
            </div>
            <div style="background: #f9f9f9; border-radius: 0 0 10px 10px; padding: 30px;">
                <h2 style="color: #333; margin-top: 0;">重置您的密码 / Reset Your Password</h2>
                <p>您好，<strong>"""
            + username
            + """</strong>！</p>
                <p>Hello, <strong>"""
            + username
            + """</strong>!</p>
                <p>我们收到了重置您密码的请求。请点击下方按钮重置密码：</p>
                <p>We received a request to reset your password. Please click the button below to reset it:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href=\""""
            + reset_url
            + """\" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">重置密码 / Reset Password</a>
                </div>
                <p style="color: #666; font-size: 14px;">此链接将在 """
            + expire_hours
            + """ 小时后失效。</p>
                <p style="color: #666; font-size: 14px;">This link will expire in """
            + expire_hours
            + """ hours.</p>
            </div>
        </body>
        </html>
        """
        )

        text_content = (
            from_name
            + """ - 重置密码 / Password Reset

您好，"""
            + username
            + """！

请访问以下链接重置密码：
"""
            + reset_url
            + """

此链接将在 """
            + expire_hours
            + """ 小时后失效。
"""
        )

        try:
            params: resend.Emails.SendParams = {
                "from": self._get_from_address(account),
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
            }
            response = resend.Emails.send(params)
            masked_key = self._mask_api_key(account["api_key"])
            logger.info(
                "[EmailService] Password reset email sent to %s via key %s, id=%s",
                to_email,
                masked_key,
                response.get("id", "unknown"),
            )
            return True
        except Exception as e:
            logger.error(
                "[EmailService] Failed to send password reset email to %s: %s",
                to_email,
                e,
            )
            return False

    async def send_verification_email(
        self, to_email: str, username: str, verify_token: str, base_url: str
    ) -> bool:
        """Send email verification email.

        Args:
            to_email: Recipient email address.
            username: User's username for personalization.
            verify_token: Email verification token.
            base_url: Base URL for constructing verify link.

        Returns:
            True if email sent successfully, False otherwise.
        """
        if not self.is_enabled():
            logger.warning("[EmailService] Cannot send email: service not enabled")
            return False

        account = self._get_next_account()
        if not account:
            logger.warning("[EmailService] No accounts available")
            return False

        resend.api_key = account["api_key"]
        verify_url = base_url.rstrip("/") + "/verify-email?token=" + verify_token
        from_name = account.get("email_from_name", "LambChat")

        subject = from_name + " - 验证您的邮箱 / Verify Your Email"

        html_content = (
            """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0; padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">✉️ """
            + from_name
            + """</h1>
            </div>
            <div style="background: #f9f9f9; border-radius: 0 0 10px 10px; padding: 30px;">
                <h2 style="color: #333; margin-top: 0;">验证您的邮箱 / Verify Your Email</h2>
                <p>您好，<strong>"""
            + username
            + """</strong>！</p>
                <p>Hello, <strong>"""
            + username
            + """</strong>!</p>
                <p>感谢您注册 """
            + from_name
            + """！请点击下方按钮验证您的邮箱地址：</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href=\""""
            + verify_url
            + """\" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">验证邮箱 / Verify Email</a>
                </div>
            </div>
        </body>
        </html>
        """
        )

        text_content = (
            from_name
            + """ - 验证您的邮箱 / Verify Your Email

您好，"""
            + username
            + """！

请访问以下链接验证您的邮箱地址：
"""
            + verify_url
        )

        try:
            params: resend.Emails.SendParams = {
                "from": self._get_from_address(account),
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
            }
            response = resend.Emails.send(params)
            masked_key = self._mask_api_key(account["api_key"])
            logger.info(
                "[EmailService] Verification email sent to %s via key %s, id=%s",
                to_email,
                masked_key,
                response.get("id", "unknown"),
            )
            return True
        except Exception as e:
            logger.error(
                "[EmailService] Failed to send verification email to %s: %s",
                to_email,
                e,
            )
            return False

    async def send_welcome_email(self, to_email: str, username: str, base_url: str) -> bool:
        """Send welcome email after registration.

        Args:
            to_email: Recipient email address.
            username: User's username for personalization.
            base_url: Base URL for constructing login link.

        Returns:
            True if email sent successfully, False otherwise.
        """
        if not self.is_enabled():
            logger.warning("[EmailService] Cannot send email: service not enabled")
            return False

        account = self._get_next_account()
        if not account:
            logger.warning("[EmailService] No accounts available")
            return False

        resend.api_key = account["api_key"]
        login_url = base_url.rstrip("/") + "/login"
        from_name = account.get("email_from_name", "LambChat")

        subject = "欢迎加入 " + from_name + "！/ Welcome to " + from_name + "!"

        html_content = (
            """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0; padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">🎉 """
            + from_name
            + """</h1>
            </div>
            <div style="background: #f9f9f9; border-radius: 0 0 10px 10px; padding: 30px;">
                <h2 style="color: #333; margin-top: 0;">欢迎加入！/ Welcome!</h2>
                <p>您好，<strong>"""
            + username
            + """</strong>！</p>
                <p>Hello, <strong>"""
            + username
            + """</strong>!</p>
                <p>欢迎加入 """
            + from_name
            + """！</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href=\""""
            + login_url
            + """\" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">开始使用 / Get Started</a>
                </div>
            </div>
        </body>
        </html>
        """
        )

        text_content = (
            """欢迎加入 """
            + from_name
            + """！

您好，"""
            + username
            + """！

立即登录开始使用："""
            + login_url
        )

        try:
            params: resend.Emails.SendParams = {
                "from": self._get_from_address(account),
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
            }
            response = resend.Emails.send(params)
            masked_key = self._mask_api_key(account["api_key"])
            logger.info(
                "[EmailService] Welcome email sent to %s via key %s, id=%s",
                to_email,
                masked_key,
                response.get("id", "unknown"),
            )
            return True
        except Exception as e:
            logger.error(
                "[EmailService] Failed to send welcome email to %s: %s",
                to_email,
                e,
            )
            return False


def get_email_service() -> EmailService:
    """Get the singleton EmailService instance."""
    return EmailService.get_instance()
