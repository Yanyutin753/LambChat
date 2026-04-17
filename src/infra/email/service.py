"""Resend email service implementation."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from email.utils import formataddr
from typing import Optional

import httpx

from src.infra.email.template import EmailTemplate
from src.infra.email.texts import get_texts
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


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
    _lock = asyncio.Lock()
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
                if self._http_client is None:
                    self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    def _parse_accounts(self) -> list[dict[str, str]]:
        """Parse account configurations from RESEND_ACCOUNTS JSON."""
        accounts: list[dict[str, str]] = []
        resend_accounts = settings.RESEND_ACCOUNTS
        if not resend_accounts:
            return accounts

        try:
            if isinstance(resend_accounts, str):
                resend_accounts = json.loads(resend_accounts)
            if isinstance(resend_accounts, list):
                for acc in resend_accounts:
                    if isinstance(acc, dict) and acc.get("api_key"):
                        accounts.append(
                            {
                                "api_key": str(acc.get("api_key", "")),
                                "email_from": str(acc.get("email_from", "noreply@example.com")),
                                "email_from_name": str(acc.get("email_from_name", "LambChat")),
                            }
                        )
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("[EmailService] Failed to parse RESEND_ACCOUNTS: %s", e)

        return accounts

    async def _get_accounts(self) -> list[dict[str, str]]:
        """Get accounts with hot-reload support."""
        if self._accounts_cache is not None and time.time() - self._config_loaded_at < 60:
            return self._accounts_cache

        async with self._lock:
            if self._accounts_cache is not None and time.time() - self._config_loaded_at < 60:
                return self._accounts_cache

            self._accounts_cache = self._parse_accounts()
            self._config_loaded_at = time.time()

            if self._accounts_cache:
                logger.info("[EmailService] Loaded %d Resend account(s)", len(self._accounts_cache))
            else:
                logger.warning("[EmailService] No accounts configured")

            return self._accounts_cache

    def _mask_api_key(self, key: str) -> str:
        """Mask API key for safe logging."""
        if not key or len(key) < 8:
            return "***"
        return key[:4] + "..." + key[-4:]

    async def _get_next_account(self) -> Optional[dict[str, str]]:
        """Get next account using round-robin rotation."""
        accounts = await self._get_accounts()
        if not accounts:
            return None
        async with self._lock:
            account = accounts[self._current_index]
            self._current_index = (self._current_index + 1) % len(accounts)
            return account.copy()

    @classmethod
    async def get_instance(cls) -> EmailService:
        """Get singleton instance of EmailService."""
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def is_enabled(self) -> bool:
        """Check if email service is enabled (config-level only).

        Note: account availability is checked separately in _get_next_account().
        """
        return self._enabled

    def _get_from_address(self, account: dict[str, str]) -> str:
        """Get formatted sender address from account."""
        return formataddr((account.get("email_from_name", ""), account.get("email_from", "")))

    def generate_token(self) -> str:
        """Generate a secure random token for password reset or email verification."""
        return secrets.token_urlsafe(32)

    def get_token_expiry(self, hours: Optional[int] = None) -> datetime:
        """Get token expiry datetime."""
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
        """Send email via Resend API using httpx with retry logic."""
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
                    last_error = Exception(f"HTTP {response.status_code}: {response.text[:200]}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                    continue
                else:
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

        logger.error(
            "[EmailService] Failed to send email to %s after %d attempts: %s",
            to_email,
            max_retries,
            last_error,
        )
        return False

    async def send_password_reset_email(
        self, to_email: str, username: str, reset_token: str, base_url: str, lang: str = "en"
    ) -> bool:
        """Send password reset email.

        Args:
            to_email: Recipient email address.
            username: User's username for personalization.
            reset_token: Password reset token.
            base_url: Base URL for constructing reset link.
            lang: 2-letter language code (en, zh, ja, ko, ru).

        Returns:
            True if email sent successfully, False otherwise.
        """
        if not self.is_enabled():
            logger.warning("[EmailService] Cannot send email: service not enabled")
            return False

        account = await self._get_next_account()
        if not account:
            logger.warning("[EmailService] No accounts available")
            return False

        reset_url = base_url.rstrip("/") + "/auth/reset-password?token=" + reset_token
        from_name = account.get("email_from_name", "LambChat")
        expire_hours = str(self._reset_expire_hours)
        icon_url = base_url.rstrip("/") + "/icons/icon.svg"
        safe_username = EmailTemplate._escape_html(username)

        texts = get_texts(lang, "password_reset")
        subject = texts["subject"].format(from_name=from_name)
        footer = (
            texts["footer"].format(from_name=from_name, hours=expire_hours)
            if texts["footer"]
            else None
        )

        html_content = EmailTemplate.render(
            title=from_name,
            icon_url=icon_url,
            heading=texts["heading"],
            greeting=texts["greeting"].format(username=safe_username),
            content=texts["content"].format(from_name=from_name),
            button_url=reset_url,
            button_text=texts["button_text"],
            footer=footer,
        )

        plain_greeting = (
            texts["greeting"]
            .replace("<strong>", "")
            .replace("</strong>", "")
            .format(username=username)
        )
        text_content = f"""{subject}

{plain_greeting}

{texts["content"].format(from_name=from_name)}

{reset_url}

{footer.replace("<br>", "\n") if footer else ""}"""

        return await self._send_email(account, to_email, subject, html_content, text_content)

    async def send_verification_email(
        self, to_email: str, username: str, verify_token: str, base_url: str, lang: str = "en"
    ) -> bool:
        """Send email verification email.

        Args:
            to_email: Recipient email address.
            username: User's username for personalization.
            verify_token: Email verification token.
            base_url: Base URL for constructing verify link.
            lang: 2-letter language code (en, zh, ja, ko, ru).

        Returns:
            True if email sent successfully, False otherwise.
        """
        if not self.is_enabled():
            logger.warning("[EmailService] Cannot send email: service not enabled")
            return False

        account = await self._get_next_account()
        if not account:
            logger.warning("[EmailService] No accounts available")
            return False

        verify_url = (
            base_url.rstrip("/") + "/auth/verify-email?token=" + verify_token + "&email=" + to_email
        )
        from_name = account.get("email_from_name", "LambChat")
        icon_url = base_url.rstrip("/") + "/icons/icon.svg"
        safe_username = EmailTemplate._escape_html(username)

        texts = get_texts(lang, "verify_email")
        subject = texts["subject"].format(from_name=from_name)
        footer = texts["footer"].format(from_name=from_name) if texts["footer"] else None

        html_content = EmailTemplate.render(
            title=from_name,
            icon_url=icon_url,
            heading=texts["heading"],
            greeting=texts["greeting"].format(username=safe_username),
            content=texts["content"].format(from_name=from_name),
            button_url=verify_url,
            button_text=texts["button_text"],
            footer=footer,
        )

        plain_greeting = (
            texts["greeting"]
            .replace("<strong>", "")
            .replace("</strong>", "")
            .format(username=username)
        )
        text_content = f"""{subject}

{plain_greeting}

{texts["content"].format(from_name=from_name)}

{verify_url}

{footer.replace("<br>", "\n") if footer else ""}"""

        return await self._send_email(account, to_email, subject, html_content, text_content)

    async def send_welcome_email(
        self, to_email: str, username: str, base_url: str, lang: str = "en"
    ) -> bool:
        """Send welcome email after registration.

        Args:
            to_email: Recipient email address.
            username: User's username for personalization.
            base_url: Base URL for constructing login link.
            lang: 2-letter language code (en, zh, ja, ko, ru).

        Returns:
            True if email sent successfully, False otherwise.
        """
        if not self.is_enabled():
            logger.warning("[EmailService] Cannot send email: service not enabled")
            return False

        account = await self._get_next_account()
        if not account:
            logger.warning("[EmailService] No accounts available")
            return False

        login_url = base_url.rstrip("/") + "/auth/login"
        from_name = account.get("email_from_name", "LambChat")
        icon_url = base_url.rstrip("/") + "/icons/icon.svg"
        safe_username = EmailTemplate._escape_html(username)

        texts = get_texts(lang, "welcome")
        subject = texts["subject"].format(from_name=from_name)

        html_content = EmailTemplate.render(
            title=from_name,
            icon_url=icon_url,
            heading=texts["heading"],
            greeting=texts["greeting"].format(username=safe_username),
            content=texts["content"].format(from_name=from_name),
            button_url=login_url,
            button_text=texts["button_text"],
        )

        plain_greeting = (
            texts["greeting"]
            .replace("<strong>", "")
            .replace("</strong>", "")
            .format(username=username)
        )
        text_content = f"""{subject}

{plain_greeting}

{texts["content"].format(from_name=from_name)}

{login_url}
"""

        return await self._send_email(account, to_email, subject, html_content, text_content)

    async def close(self) -> None:
        """Close the HTTP client and cleanup resources."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
            logger.info("[EmailService] HTTP client closed")


async def get_email_service() -> EmailService:
    """Get the singleton EmailService instance."""
    return await EmailService.get_instance()
