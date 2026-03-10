"""Resend email service implementation."""

from __future__ import annotations

import logging
import secrets
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
    """

    _instance: Optional[EmailService] = None

    def __init__(self) -> None:
        """Initialize the email service."""
        self._enabled = settings.EMAIL_ENABLED
        self._api_key = settings.RESEND_API_KEY
        self._from_email = settings.EMAIL_FROM
        self._from_name = settings.EMAIL_FROM_NAME
        self._reset_expire_hours = settings.PASSWORD_RESET_EXPIRE_HOURS

        if self._enabled and self._api_key:
            resend.api_key = self._api_key
            logger.info("[EmailService] Initialized with Resend API")
        elif self._enabled:
            logger.warning(
                "[EmailService] Email enabled but RESEND_API_KEY not configured"
            )
        else:
            logger.info("[EmailService] Email service disabled")

    @classmethod
    def get_instance(cls) -> EmailService:
        """Get singleton instance of EmailService."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_enabled(self) -> bool:
        """Check if email service is enabled and configured."""
        return self._enabled and bool(self._api_key)

    def _get_from_address(self) -> str:
        """Get formatted sender address."""
        return formataddr((self._from_name, self._from_email))

    def generate_token(self) -> str:
        """Generate a secure random token for password reset or email verification."""
        return secrets.token_urlsafe(32)

    def get_token_expiry(self, hours: Optional[int] = None) -> datetime:
        """Get token expiry datetime.

        Args:
            hours: Number of hours until expiry. Defaults to PASSWORD_RESET_EXPIRE_HOURS.

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

        reset_url = f"{base_url.rstrip('/')}/reset-password?token={reset_token}"

        subject = f"{self._from_name} - 重置密码 / Password Reset"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0; padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">🔐 {self._from_name}</h1>
            </div>
            <div style="background: #f9f9f9; border-radius: 0 0 10px 10px; padding: 30px;">
                <h2 style="color: #333; margin-top: 0;">重置您的密码 / Reset Your Password</h2>
                <p>您好，<strong>{username}</strong>！</p>
                <p>Hello, <strong>{username}</strong>!</p>
                <p>我们收到了重置您密码的请求。请点击下方按钮重置密码：</p>
                <p>We received a request to reset your password. Please click the button below to reset it:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">重置密码 / Reset Password</a>
                </div>
                <p style="color: #666; font-size: 14px;">或者复制以下链接到浏览器：<br><code style="word-break: break-all; background: #eee; padding: 2px 6px; border-radius: 4px;">{reset_url}</code></p>
                <p style="color: #666; font-size: 14px;">此链接将在 {self._reset_expire_hours} 小时后失效。</p>
                <p style="color: #666; font-size: 14px;">This link will expire in {self._reset_expire_hours} hours.</p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    如果您没有请求重置密码，请忽略此邮件。<br>
                    If you didn't request this, please ignore this email.
                </p>
            </div>
        </body>
        </html>
        """

        text_content = f"""
{self._from_name} - 重置密码 / Password Reset

您好，{username}！

我们收到了重置您密码的请求。请访问以下链接重置密码：
{reset_url}

此链接将在 {self._reset_expire_hours} 小时后失效。

如果您没有请求重置密码，请忽略此邮件。
"""

        try:
            params: resend.Emails.SendParams = {
                "from": self._get_from_address(),
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
            }
            response = resend.Emails.send(params)
            logger.info(
                "[EmailService] Password reset email sent to %s, id=%s",
                to_email,
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

        verify_url = f"{base_url.rstrip('/')}/verify-email?token={verify_token}"

        subject = f"{self._from_name} - 验证您的邮箱 / Verify Your Email"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0; padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">✉️ {self._from_name}</h1>
            </div>
            <div style="background: #f9f9f9; border-radius: 0 0 10px 10px; padding: 30px;">
                <h2 style="color: #333; margin-top: 0;">验证您的邮箱 / Verify Your Email</h2>
                <p>您好，<strong>{username}</strong>！</p>
                <p>Hello, <strong>{username}</strong>!</p>
                <p>感谢您注册 {self._from_name}！请点击下方按钮验证您的邮箱地址：</p>
                <p>Thank you for registering at {self._from_name}! Please click the button below to verify your email address:</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{verify_url}" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">验证邮箱 / Verify Email</a>
                </div>
                <p style="color: #666; font-size: 14px;">或者复制以下链接到浏览器：<br><code style="word-break: break-all; background: #eee; padding: 2px 6px; border-radius: 4px;">{verify_url}</code></p>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    如果您没有注册账户，请忽略此邮件。<br>
                    If you didn't create an account, please ignore this email.
                </p>
            </div>
        </body>
        </html>
        """

        text_content = f"""
{self._from_name} - 验证您的邮箱 / Verify Your Email

您好，{username}！

感谢您注册 {self._from_name}！请访问以下链接验证您的邮箱地址：
{verify_url}

如果您没有注册账户，请忽略此邮件。
"""

        try:
            params: resend.Emails.SendParams = {
                "from": self._get_from_address(),
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
            }
            response = resend.Emails.send(params)
            logger.info(
                "[EmailService] Verification email sent to %s, id=%s",
                to_email,
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

    async def send_welcome_email(
        self, to_email: str, username: str, base_url: str
    ) -> bool:
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

        login_url = f"{base_url.rstrip('/')}/login"

        subject = f"欢迎加入 {self._from_name}！/ Welcome to {self._from_name}!"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0; padding: 30px; text-align: center;">
                <h1 style="color: white; margin: 0; font-size: 24px;">🎉 {self._from_name}</h1>
            </div>
            <div style="background: #f9f9f9; border-radius: 0 0 10px 10px; padding: 30px;">
                <h2 style="color: #333; margin-top: 0;">欢迎加入！/ Welcome!</h2>
                <p>您好，<strong>{username}</strong>！</p>
                <p>Hello, <strong>{username}</strong>!</p>
                <p>欢迎加入 {self._from_name}！我们很高兴您成为我们的一员。</p>
                <p>Welcome to {self._from_name}! We're glad to have you here.</p>
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{login_url}" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">开始使用 / Get Started</a>
                </div>
                <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
                <p style="color: #999; font-size: 12px; text-align: center;">
                    如有任何问题，请随时联系我们的支持团队。<br>
                    If you have any questions, please feel free to contact our support team.
                </p>
            </div>
        </body>
        </html>
        """

        text_content = f"""
欢迎加入 {self._from_name}！/ Welcome to {self._from_name}!

您好，{username}！

欢迎加入 {self._from_name}！我们很高兴您成为我们的一员。

立即登录开始使用：{login_url}

如有任何问题，请随时联系我们的支持团队。
"""

        try:
            params: resend.Emails.SendParams = {
                "from": self._get_from_address(),
                "to": [to_email],
                "subject": subject,
                "html": html_content,
                "text": text_content,
            }
            response = resend.Emails.send(params)
            logger.info(
                "[EmailService] Welcome email sent to %s, id=%s",
                to_email,
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
