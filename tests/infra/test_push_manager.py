from __future__ import annotations

import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pywebpush import WebPushException

from src.infra.push.manager import PushManager
from src.kernel.schemas.push_subscription import PushSubscription, PushSubscriptionKeys


def _make_subscription(
    endpoint: str = "https://push.example.com/sub/1",
) -> PushSubscription:
    return PushSubscription(
        id="sub-1",
        user_id="user-1",
        endpoint=endpoint,
        keys=PushSubscriptionKeys(p256dh="key", auth="auth"),
        user_agent="Mozilla/5.0",
        created_at=datetime(2026, 1, 15),
    )


def _fake_settings(**overrides) -> type:
    defaults = {
        "VAPID_PUBLIC_KEY": "pub-key",
        "VAPID_PRIVATE_KEY": "priv-key",
        "VAPID_SUBJECT": "mailto:admin@example.com",
    }
    defaults.update(overrides)
    return type("S", (), defaults)()


@pytest.mark.asyncio
async def test_send_push_returns_zero_when_vapid_not_configured() -> None:
    manager = PushManager()
    manager._settings = _fake_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")

    with patch("src.infra.push.manager.settings", manager._settings):
        count = await manager.send_push_to_user("user-1", {"title": "Test"})
    assert count == 0


@pytest.mark.asyncio
async def test_send_push_returns_zero_when_no_subscriptions() -> None:
    manager = PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[])

    with patch("src.infra.push.manager.settings", _fake_settings()):
        count = await manager.send_push_to_user("user-1", {"title": "Test"})
    assert count == 0


@pytest.mark.asyncio
@patch("pywebpush.webpush")
async def test_send_push_delivers_to_subscriptions(mock_webpush: MagicMock) -> None:
    manager = PushManager()
    subs = [_make_subscription(), _make_subscription(endpoint="https://push.example.com/sub/2")]
    manager.storage.get_by_user = AsyncMock(return_value=subs)
    manager.storage.touch_last_used = AsyncMock()

    with patch("src.infra.push.manager.settings", _fake_settings()):
        count = await manager.send_push_to_user("user-1", {"title": "Hello", "body": "World"})

    assert count == 2
    assert mock_webpush.call_count == 2
    call1 = mock_webpush.call_args_list[0]
    call2 = mock_webpush.call_args_list[1]
    assert call1.kwargs["subscription_info"]["endpoint"] == "https://push.example.com/sub/1"
    assert call2.kwargs["subscription_info"]["endpoint"] == "https://push.example.com/sub/2"
    # Verify payload
    import json

    payload = json.loads(call1.kwargs["data"])
    assert payload == {"title": "Hello", "body": "World"}
    assert manager.storage.touch_last_used.call_count == 2


@pytest.mark.asyncio
@patch("pywebpush.webpush")
async def test_send_push_removes_gone_subscriptions(mock_webpush: MagicMock) -> None:
    """410 Gone should trigger subscription removal."""
    manager = PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[_make_subscription()])
    manager.storage.delete_by_endpoint = AsyncMock()

    err = Exception("Gone")
    err.status_code = 410
    mock_webpush.side_effect = err

    with patch("src.infra.push.manager.settings", _fake_settings()):
        count = await manager.send_push_to_user("user-1", {"title": "Test"})

    assert count == 0
    manager.storage.delete_by_endpoint.assert_called_once_with("https://push.example.com/sub/1")


@pytest.mark.asyncio
@patch("pywebpush.webpush")
async def test_send_push_removes_404_subscriptions(mock_webpush: MagicMock) -> None:
    """404 should also trigger subscription removal."""
    manager = PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[_make_subscription()])
    manager.storage.delete_by_endpoint = AsyncMock()

    err = Exception("Not Found")
    err.status_code = 404
    mock_webpush.side_effect = err

    with patch("src.infra.push.manager.settings", _fake_settings()):
        count = await manager.send_push_to_user("user-1", {"title": "Test"})

    assert count == 0
    manager.storage.delete_by_endpoint.assert_called_once_with("https://push.example.com/sub/1")


@pytest.mark.asyncio
@patch("pywebpush.webpush")
async def test_send_push_removes_real_webpush_gone_subscriptions(
    mock_webpush: MagicMock,
) -> None:
    """pywebpush stores status_code on exception.response, not on the exception."""
    manager = PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[_make_subscription()])
    manager.storage.delete_by_endpoint = AsyncMock()

    response = MagicMock()
    response.status_code = 410
    response.text = "gone"
    mock_webpush.side_effect = WebPushException("Gone", response=response)

    with patch("src.infra.push.manager.settings", _fake_settings()):
        count = await manager.send_push_to_user("user-1", {"title": "Test"})

    assert count == 0
    manager.storage.delete_by_endpoint.assert_called_once_with("https://push.example.com/sub/1")


@pytest.mark.asyncio
@patch("pywebpush.webpush")
async def test_send_push_skips_other_errors(mock_webpush: MagicMock) -> None:
    """Non-4xx errors should not remove the subscription."""
    manager = PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[_make_subscription()])
    manager.storage.delete_by_endpoint = AsyncMock()

    mock_webpush.side_effect = ConnectionError("Network error")

    with patch("src.infra.push.manager.settings", _fake_settings()):
        count = await manager.send_push_to_user("user-1", {"title": "Test"})

    assert count == 0
    manager.storage.delete_by_endpoint.assert_not_called()


@pytest.mark.asyncio
@patch("pywebpush.webpush")
async def test_send_push_error_log_omits_endpoint_and_exception_text(
    mock_webpush: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    endpoint = "https://push.example.com/sub/private-token"
    manager = PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[_make_subscription(endpoint)])
    manager.storage.delete_by_endpoint = AsyncMock()
    mock_webpush.side_effect = ConnectionError(f"failed endpoint={endpoint}")

    with patch("src.infra.push.manager.settings", _fake_settings()):
        await manager.send_push_to_user("user-1", {"title": "Test"})

    assert endpoint not in caplog.text
    assert "failed endpoint" not in caplog.text
    assert "ConnectionError" in caplog.text


@pytest.mark.asyncio
@patch("pywebpush.webpush")
async def test_send_push_gone_log_omits_endpoint(
    mock_webpush: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    endpoint = "https://push.example.com/sub/revoked-token"
    manager = PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[_make_subscription(endpoint)])
    manager.storage.delete_by_endpoint = AsyncMock()
    error = Exception("Gone")
    error.status_code = 410
    mock_webpush.side_effect = error

    with caplog.at_level(logging.INFO):
        with patch("src.infra.push.manager.settings", _fake_settings()):
            await manager.send_push_to_user("user-1", {"title": "Test"})

    assert endpoint not in caplog.text
    assert "HTTP 410" in caplog.text


@pytest.mark.asyncio
@patch("pywebpush.webpush")
async def test_send_push_passes_vapid_claims(mock_webpush: MagicMock) -> None:
    """Verify vapid_claims is passed correctly."""
    manager = PushManager()
    manager.storage.get_by_user = AsyncMock(return_value=[_make_subscription()])
    manager.storage.touch_last_used = AsyncMock()

    with patch(
        "src.infra.push.manager.settings",
        _fake_settings(
            VAPID_PRIVATE_KEY="my-priv-key",
            VAPID_SUBJECT="mailto:admin@example.com",
        ),
    ):
        await manager.send_push_to_user("user-1", {"title": "Test"})

    call = mock_webpush.call_args
    assert call.kwargs["vapid_private_key"] == "my-priv-key"
    assert call.kwargs["vapid_claims"] == {"sub": "mailto:admin@example.com"}


@pytest.mark.asyncio
async def test_save_subscription_delegates_to_storage() -> None:
    manager = PushManager()
    sub = _make_subscription()
    manager.storage.create = AsyncMock(return_value=sub)

    result = await manager.save_subscription(
        "user-1",
        {
            "endpoint": "https://push.example.com/sub/1",
            "keys": {"p256dh": "key", "auth": "auth"},
        },
    )

    manager.storage.create.assert_called_once_with(
        "user-1",
        {
            "endpoint": "https://push.example.com/sub/1",
            "keys": {"p256dh": "key", "auth": "auth"},
        },
        "",
    )
    assert result["id"] == "sub-1"


@pytest.mark.asyncio
async def test_remove_subscription_delegates_to_storage() -> None:
    manager = PushManager()
    manager.storage.delete_by_endpoint = AsyncMock(return_value=True)

    result = await manager.remove_subscription("https://push.example.com/sub/1")

    assert result is True
    manager.storage.delete_by_endpoint.assert_called_once_with("https://push.example.com/sub/1")


@pytest.mark.asyncio
async def test_remove_all_for_user_delegates_to_storage() -> None:
    manager = PushManager()
    manager.storage.delete_by_user = AsyncMock(return_value=3)

    result = await manager.remove_all_for_user("user-1")

    assert result == 3
    manager.storage.delete_by_user.assert_called_once_with("user-1")


@pytest.mark.asyncio
async def test_close_delegates_to_storage() -> None:
    manager = PushManager()
    manager.storage.close = AsyncMock()

    await manager.close()

    manager.storage.close.assert_called_once()
