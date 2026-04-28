from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _coerce_now(now: datetime | None) -> datetime:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current


def _resolve_timezone(user_timezone: str | None) -> tuple[tzinfo, str]:
    timezone_name = (user_timezone or "").strip()
    if timezone_name:
        try:
            return ZoneInfo(timezone_name), timezone_name
        except ZoneInfoNotFoundError:
            pass
    return timezone.utc, "UTC"


def _format_offset(current: datetime) -> str:
    offset = current.strftime("%z")
    if len(offset) == 5:
        return f"{offset[:3]}:{offset[3:]}"
    return "+00:00"


def format_user_message_with_timestamp(
    content: str,
    user_timezone: str | None,
    now: datetime | None = None,
) -> str:
    current = _coerce_now(now)
    tz, timezone_label = _resolve_timezone(user_timezone)
    localized = current.astimezone(tz)
    timestamp = localized.strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp} {_format_offset(localized)} {timezone_label}] {content}"
