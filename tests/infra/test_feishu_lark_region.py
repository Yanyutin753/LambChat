"""Feishu and international Lark keep credentials on the selected endpoint."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from src.infra.channel.feishu.channel import FeishuChannel
from src.infra.channel.feishu.manager import FeishuChannelManager
from src.kernel.schemas.feishu import FeishuConfig


@pytest.mark.parametrize(
    "platform,host",
    [
        ("feishu", "open.feishu.cn"),
        ("lark", "open.larksuite.com"),
    ],
)
async def test_region_applies_to_sdk_http_and_websocket(monkeypatch, platform, host):
    config = FeishuConfig(
        user_id="owner", app_id="cli_test", app_secret="secret", platform=platform
    )
    channel = FeishuChannel(config)
    loop = asyncio.get_running_loop()
    monkeypatch.setattr("src.infra.channel.feishu.channel._ensure_feishu_ws_loop", lambda: loop)

    def discard_background(coroutine, target_loop):
        coroutine.close()
        return None

    monkeypatch.setattr("asyncio.run_coroutine_threadsafe", discard_background)
    assert await channel.start()
    try:
        assert channel._client._config.domain == f"https://{host}"
        channel._running = False
        await channel._run_ws_client(event_handler=object())
        assert channel._ws_client._domain == f"https://{host}"
    finally:
        channel._running = False


@pytest.mark.parametrize(
    "platform,host",
    [
        ("feishu", "open.feishu.cn"),
        ("lark", "open.larksuite.com"),
    ],
)
async def test_region_applies_to_tenant_token_and_cardkit(platform, host):
    channel = FeishuChannel(
        FeishuConfig(
            user_id="owner",
            app_id="cli_test",
            app_secret="secret",
            platform=platform,
        )
    )
    requests = []

    def receive(request):
        requests.append(request)
        if "/auth/" in request.url.path:
            return httpx.Response(200, json={"code": 0, "tenant_access_token": platform + "-token"})
        assert request.headers["authorization"] == f"Bearer {platform}-token"
        return httpx.Response(200, json={"code": 0, "data": {"card_id": "card"}})

    channel._feishu_http_client = httpx.AsyncClient(transport=httpx.MockTransport(receive))
    try:
        result = await channel._feishu_json(
            "POST", "/cardkit/v1/cards", json_body={"type": "card_json"}
        )
        assert result["data"]["card_id"] == "card"
        assert [request.url.host for request in requests] == [host, host]
    finally:
        await channel.close_feishu_http_client()


def test_region_defaults_to_china_and_cannot_be_arbitrary_url():
    config = FeishuConfig(user_id="owner", app_id="app", app_secret="secret")
    assert config.platform == "feishu"
    with pytest.raises(ValidationError):
        FeishuConfig(
            user_id="owner", app_id="app", app_secret="secret", platform="https://attacker.test"
        )


def test_manager_preserves_region_when_loading_saved_config():
    config = FeishuChannelManager()._dict_to_config(
        "owner",
        {
            "app_id": "app",
            "app_secret": "secret",
            "platform": "lark",
            "instance_id": "instance",
        },
    )
    assert config.platform == "lark"


async def test_legacy_storage_roundtrips_region_without_dropping_updates():
    from src.infra.channel.feishu.storage import FeishuStorage
    from src.kernel.schemas.feishu import FeishuConfigCreate, FeishuConfigUpdate

    documents = []

    async def find_one(query):
        return documents[0] if documents else None

    async def insert_one(document):
        documents.append(document)

    async def update_one(query, update):
        documents[0].update(update["$set"])

    storage = FeishuStorage()
    storage._collection = AsyncMock()
    storage._collection.find_one.side_effect = find_one
    storage._collection.insert_one.side_effect = insert_one
    storage._collection.update_one.side_effect = update_one
    storage._encrypt_secret = AsyncMock(return_value="encrypted")
    storage._decrypt_secret = AsyncMock(return_value="secret")
    created = await storage.create_config(
        FeishuConfigCreate(
            app_id="app",
            app_secret="secret",
            platform="lark",
        ),
        "owner",
    )
    assert created.platform == "lark"
    assert (await storage.get_response("owner")).platform == "lark"
    assert (
        await storage.update_config("owner", FeishuConfigUpdate(platform="feishu"))
    ).platform == "feishu"
