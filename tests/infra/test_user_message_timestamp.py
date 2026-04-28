from datetime import datetime, timezone

from src.infra.chat.user_message_timestamp import format_user_message_with_timestamp


def test_format_user_message_with_timestamp_uses_user_timezone() -> None:
    formatted = format_user_message_with_timestamp(
        "hello",
        user_timezone="Asia/Shanghai",
        now=datetime(2026, 4, 28, 12, 34, 56, tzinfo=timezone.utc),
    )

    assert formatted == "[2026-04-28 20:34:56 +08:00 Asia/Shanghai] hello"


def test_format_user_message_with_timestamp_falls_back_to_utc() -> None:
    formatted = format_user_message_with_timestamp(
        "hello",
        user_timezone="Mars/Olympus",
        now=datetime(2026, 4, 28, 12, 34, 56, tzinfo=timezone.utc),
    )

    assert formatted == "[2026-04-28 12:34:56 +00:00 UTC] hello"
