"""Resend email service implementation."""

from __future__ import annotations

import asyncio
import html
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from email.utils import formataddr
from typing import Optional

import httpx

from src.kernel.config import settings

logger = logging.getLogger(__name__)

# Resend API endpoint
RESEND_API_URL = "https://api.resend.com/emails"


class EmailTemplate:
    """Email template renderer with consistent styling."""

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters to prevent XSS attacks.

        Args:
            text: Text to escape

        Returns:
            HTML-escaped text safe for insertion into HTML
        """
        return html.escape(str(text), quote=True)

    @staticmethod
    def _escape_url(url: str) -> str:
        """Validate and escape URL to prevent javascript: and data: URL attacks.

        Args:
            url: URL to validate and escape

        Returns:
            Safe URL or empty string if invalid
        """
        url = str(url).strip()
        # Only allow http and https protocols
        if url.startswith(("http://", "https://")):
            return html.escape(url, quote=True)
        # Block dangerous protocols
        logger.warning("[EmailTemplate] Blocked potentially unsafe URL: %s", url[:50])
        return ""

    @staticmethod
    def render(
        title: str,
        icon: str,
        heading: str,
        greeting: str,
        content: str,
        button_url: str,
        button_text: str,
        footer: Optional[str] = None,
    ) -> str:
        """Render HTML email template with XSS protection.

        All user-provided content is HTML-escaped to prevent XSS attacks.

        Args:
            title: Email title in header
            icon: Emoji icon
            heading: Main heading
            greeting: Greeting text with username
            content: Main content paragraph
            button_url: Button link URL (validated to only allow http/https)
            button_text: Button text
            footer: Optional footer text

        Returns:
            Complete HTML email content.
        """
        # Escape all user-provided content to prevent XSS
        safe_title = EmailTemplate._escape_html(title)
        safe_icon = EmailTemplate._escape_html(icon)
        safe_heading = EmailTemplate._escape_html(heading)
        safe_greeting = EmailTemplate._escape_html(greeting)
        safe_content = EmailTemplate._escape_html(content)
        safe_button_url = EmailTemplate._escape_url(button_url)
        safe_button_text = EmailTemplate._escape_html(button_text)

        footer_html = ""
        if footer:
            safe_footer = EmailTemplate._escape_html(footer)
            footer_html = f'<p style="color: #666; font-size: 14px;">{safe_footer}</p>'

        # If button_url is invalid, render button without link
        button_html = ""
        if safe_button_url:
            button_html = f'<a href="{safe_button_url}" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">{safe_button_text}</a>'
        else:
            button_html = f'<span style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 14px 28px; text-decoration: none; border-radius: 6px; display: inline-block; font-weight: bold;">{safe_button_text}</span>'

        return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 10px 10px 0 0; padding: 30px; text-align: center;">
        <h1 style="color: white; margin: 0; font-size: 24px;">{safe_icon} {safe_title}</h1>
    </div>
    <div style="background: #f9f9f9; border-radius: 0 0 10px 10px; padding: 30px;">
        <h2 style="color: #333; margin-top: 0;">{safe_heading}</h2>
        <p>{safe_greeting}</p>
        <p>{safe_content}</p>
        <div style="text-align: center; margin: 30px 0;">
            {button_html}
        </div>
        {footer_html}
    </div>
</body>
</html>
"""


class EmailService:
    """Email service using Resend API.

    Provides email functionality for:
    - Password reset
    - Email verification
    - Welcome emails

    Supports multiple accounts with round-robin rotation.
    Each account can have its own API key and sender address.

    Uses httpx for direct API calls to avoid global state issues.
    """

    _instance: Optional[EmailService] = None
    _lock = threading.Lock()
    _http_client_lock = asyncio.Lock()

    def __init__(self) -> None:
        """Initialize the email service."""
        self._enabled = settings.EMAIL_ENABLED
        self._accounts_cache: Optional[list[dict[str, str]]] = None
        self._config_loaded_at: float = 0
        self._current_index = 0
        self._reset_expire_hours = settings.PASSWORD_RESET_EXPIRE_HOURS
        self._http_client: Optional[httpx.AsyncClient] = None

        if self._enabled:
            logger.info("[EmailService] Email service enabled")
        else:
            logger.info("[EmailService] Email service disabled")

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client lazily with thread-safe initialization."""
        if self._http_client is None:
            async with self._http_client_lock:
                # Double-check after acquiring lock
                if self._http_client is None:
                    self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

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

    def _get_accounts(self) -> list[dict[str, str]]:
        """Get accounts with hot-reload support.

        Reloads accounts from settings if config may have changed.
        Thread-safe with double-checked locking.

        Returns:
            List of account dicts.
        """
        # Quick check without lock (hot path)
        if self._accounts_cache is not None:
            # Check if we should refresh (every 60 seconds)
            if time.time() - self._config_loaded_at < 60:
                return self._accounts_cache

        with self._lock:
            # Double-check after acquiring lock
            if self._accounts_cache is not None and time.time() - self._config_loaded_at < 60:
                return self._accounts_cache

            # Parse fresh accounts
            self._accounts_cache = self._parse_accounts()
            self._config_loaded_at = time.time()

            if self._accounts_cache:
                logger.info(
                    "[EmailService] Loaded %d Resend account(s)",
                    len(self._accounts_cache),
                )
            else:
                logger.warning("[EmailService] No accounts configured")

            return self._accounts_cache

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
        accounts = self._get_accounts()
        if not accounts:
            return None

        with self._lock:
            account = accounts[self._current_index]
            self._current_index = (self._current_index + 1) % len(accounts)
            return account.copy()

    @classmethod
    def get_instance(cls) -> EmailService:
        """Get singleton instance of EmailService.

        Thread-safe with double-checked locking.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def is_enabled(self) -> bool:
        """Check if email service is enabled and configured."""
        return self._enabled and bool(self._get_accounts())

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

    async def _send_email(
        self,
        account: dict[str, str],
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str,
        max_retries: int = 3,
    ) -> bool:
        """Send email via Resend API using httpx with retry logic.

        Args:
            account: Account dict with api_key.
            to_email: Recipient email address.
            subject: Email subject.
            html_content: HTML content.
            text_content: Plain text content.
            max_retries: Maximum number of retry attempts (default: 3)

        Returns:
            True if email sent successfully, False otherwise.
        """
        last_error: Optional[Exception] = None

        for attempt in range(max_retries):
            try:
                client = await self._get_http_client()
                response = await client.post(
                    RESEND_API_URL,
                    headers={
                        "Authorization": f"Bearer {account['api_key']}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": self._get_from_address(account),
                        "to": [to_email],
                        "subject": subject,
                        "html": html_content,
                        "text": text_content,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    masked_key = self._mask_api_key(account["api_key"])
                    logger.info(
                        "[EmailService] Email sent to %s via key %s, id=%s",
                        to_email,
                        masked_key,
                        data.get("id", "unknown"),
                    )
                    return True
                elif response.status_code == 429:
                    # Rate limit - exponential backoff
                    retry_after = int(response.headers.get("Retry-After", 60))
                    wait_time = min(retry_after, 2**attempt * 5)
                    logger.warning(
                        "[EmailService] Rate limited sending to %s, waiting %ds (attempt %d/%d)",
                        to_email,
                        wait_time,
                        attempt + 1,
                        max_retries,
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                    continue
                elif response.status_code >= 500:
                    # Server error - retry with exponential backoff
                    wait_time = 2**attempt
                    logger.error(
                        "[EmailService] Server error (HTTP %d) sending to %s, retrying in %ds (attempt %d/%d): %s",
                        response.status_code,
                        to_email,
                        wait_time,
                        attempt + 1,
                        max_retries,
                        response.text[:200],
                    )
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                    last_error = Exception(f"HTTP {response.status_code}: {response.text[:200]}")
                    continue
                else:
                    # Client error (4xx) - don't retry
                    logger.error(
                        "[EmailService] Failed to send email to %s: HTTP %d - %s",
                        to_email,
                        response.status_code,
                        response.text[:200],
                    )
                    return False

            except httpx.TimeoutException as e:
                wait_time = 2**attempt
                logger.warning(
                    "[EmailService] Timeout sending to %s, retrying in %ds (attempt %d/%d): %s",
                    to_email,
                    wait_time,
                    attempt + 1,
                    max_retries,
                    str(e),
                )
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                continue

            except httpx.NetworkError as e:
                wait_time = 2**attempt
                logger.warning(
                    "[EmailService] Network error sending to %s, retrying in %ds (attempt %d/%d): %s",
                    to_email,
                    wait_time,
                    attempt + 1,
                    max_retries,
                    str(e),
                )
                last_error = e
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait_time)
                continue

            except Exception as e:
                logger.error(
                    "[EmailService] Unexpected error sending to %s: %s",
                    to_email,
                    e,
                    exc_info=True,
                )
                last_error = e
                break

        # All retries failed
        logger.error(
            "[EmailService] Failed to send email to %s after %d attempts: %s",
            to_email,
            max_retries,
            last_error,
        )
        return False

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

        reset_url = base_url.rstrip("/") + "/reset-password?token=" + reset_token
        from_name = account.get("email_from_name", "LambChat")
        expire_hours = str(self._reset_expire_hours)

        subject = f"{from_name} - 重置密码 / Password Reset"

        html_content = EmailTemplate.render(
            title=from_name,
            icon="🔐",
            heading="重置您的密码 / Reset Your Password",
            greeting=f"您好，<strong>{username}</strong>！<br>Hello, <strong>{username}</strong>!",
            content="我们收到了重置您密码的请求。请点击下方按钮重置密码：<br>We received a request to reset your password. Please click the button below to reset it:",
            button_url=reset_url,
            button_text="重置密码 / Reset Password",
            footer=f"此链接将在 {expire_hours} 小时后失效。<br>This link will expire in {expire_hours} hours.",
        )

        text_content = f"""{from_name} - 重置密码 / Password Reset

您好，{username}！

请访问以下链接重置密码：
{reset_url}

此链接将在 {expire_hours} 小时后失效。
"""

        return await self._send_email(account, to_email, subject, html_content, text_content)

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

        verify_url = (
            base_url.rstrip("/") + "/verify-email?token=" + verify_token + "&email=" + to_email
        )
        from_name = account.get("email_from_name", "LambChat")

        subject = f"{from_name} - 验证您的邮箱 / Verify Your Email"

        html_content = EmailTemplate.render(
            title=from_name,
            icon="✉️",
            heading="验证您的邮箱 / Verify Your Email",
            greeting=f"您好，<strong>{username}</strong>！<br>Hello, <strong>{username}</strong>!",
            content=f"感谢您注册 {from_name}！请点击下方按钮验证您的邮箱地址：<br>Thank you for registering with {from_name}! Please click the button below to verify your email address:",
            button_url=verify_url,
            button_text="验证邮箱 / Verify Email",
        )

        text_content = f"""{from_name} - 验证您的邮箱 / Verify Your Email

您好，{username}！

请访问以下链接验证您的邮箱地址：
{verify_url}
"""

        return await self._send_email(account, to_email, subject, html_content, text_content)

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

        login_url = base_url.rstrip("/") + "/login"
        from_name = account.get("email_from_name", "LambChat")

        subject = f"欢迎加入 {from_name}！/ Welcome to {from_name}!"

        html_content = EmailTemplate.render(
            title=from_name,
            icon="🎉",
            heading="欢迎加入！/ Welcome!",
            greeting=f"您好，<strong>{username}</strong>！<br>Hello, <strong>{username}</strong>!",
            content=f"欢迎加入 {from_name}！<br>Welcome to {from_name}!",
            button_url=login_url,
            button_text="开始使用 / Get Started",
        )

        text_content = f"""欢迎加入 {from_name}！

您好，{username}！

立即登录开始使用：{login_url}
"""

        return await self._send_email(account, to_email, subject, html_content, text_content)

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
            logger.info("[EmailService] HTTP client closed")


def get_email_service() -> EmailService:
    """Get the singleton EmailService instance."""
    return EmailService.get_instance()
