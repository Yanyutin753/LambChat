"""Startup authentication must not call the recipient-specific typing API."""

import httpx
import pytest

from src.infra.channel.weixin.provider import verify_token


@pytest.mark.parametrize(("token", "expected"), [("saved-token", True), ("expired-token", False)])
async def test_startup_authentication_without_recipient(token, expected):
    def upstream(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/getconfig"):
            return httpx.Response(200, json={"errcode": 400, "errmsg": "ilink_user_id required"})
        assert request.url.path == "/ilink/bot/msg/notifystart"
        assert request.headers["AuthorizationType"] == "ilink_bot_token"
        assert request.headers["Authorization"] == f"Bearer {token}"
        return httpx.Response(
            200,
            json={"ret": 0}
            if token == "saved-token"
            else {"errcode": -14, "errmsg": "session timeout"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(upstream)) as client:
        assert await verify_token(client, token) is expected


async def test_startup_rejects_http_failure():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(503))
    ) as client:
        assert await verify_token(client, "saved-token") is False
