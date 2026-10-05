"""Provider credentials can occur in URL paths as well as query strings."""

import logging
from unittest.mock import AsyncMock

import httpx

from src.infra.channel.telegram import TelegramChannel, TelegramConfig


async def test_http_error_logs_neither_url_credentials_nor_raw_exception(caplog):
    channel = TelegramChannel(TelegramConfig(bot_token="path-token", user_id="owner"))
    url = "https://userinfo-secret@api.telegram.org/botpath-token/sendMessage?key=query-secret"
    channel._http = AsyncMock()
    channel._http.is_closed = False
    channel._http.post.side_effect = httpx.ConnectError(f"failed for {url}")
    with caplog.at_level(logging.WARNING):
        assert await channel._post(url) is None
    for secret in ("userinfo-secret", "path-token", "query-secret"):
        assert secret not in caplog.text
    assert "api.telegram.org" in caplog.text
    assert "ConnectError" in caplog.text


async def test_send_failure_logs_exception_type_without_secret_message(caplog):
    channel = TelegramChannel(TelegramConfig(bot_token="token", user_id="owner"))
    channel._send = AsyncMock(side_effect=RuntimeError("private-secret-in-exception"))
    with caplog.at_level(logging.WARNING):
        assert not await channel.send_message("chat", "hello")
    assert "private-secret-in-exception" not in caplog.text
    assert "RuntimeError" in caplog.text
