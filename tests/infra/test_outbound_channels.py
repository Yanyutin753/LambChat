"""出站通知渠道（webhook 推送类）测试。

类似飞书的 IM 推送渠道全家桶：钉钉/企微/Telegram/Slack/Discord/ntfy/
Bark/Gotify/Pushover/Server酱/PushPlus。全部走共享 OutboundChannel 基类
（httpx.AsyncClient 异步发送、每实例懒建共享连接、超时与截断统一处理），
无长连接无入站消息，start() 即就绪。
"""

from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from src.infra.channel.registry import discover_all_channels
from src.kernel.schemas.channel import ChannelType

# ── fakes ───────────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int = 200, json_data: Any = None, text: str = ""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"HTTP {self.status_code}", request=None, response=self)


class _FakeAsyncClient:
    """可编程 httpx.AsyncClient 替身；按实例队列返回响应。"""

    def __init__(self, *args: Any, **kwargs: Any):
        self.requests: list[dict[str, Any]] = []
        self.next_responses: list[_FakeResponse] = [_FakeResponse()]
        self.closed = False

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def post(
        self,
        url: str,
        *,
        json: Any = None,
        data: Any = None,
        headers: Any = None,
        content: Any = None,
        **kwargs: Any,
    ) -> _FakeResponse:
        self.requests.append(
            {"method": "POST", "url": url, "json": json, "data": data, "headers": headers}
        )
        if self.next_responses:
            return self.next_responses.pop(0)
        return _FakeResponse()

    async def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        self.requests.append({"method": "GET", "url": url})
        return self.next_responses.pop(0) if self.next_responses else _FakeResponse()

    async def aclose(self):
        self.closed = True


@pytest.fixture()
def fake_http(monkeypatch):
    """Patch 全局 httpx.AsyncClient。

    返回 created 实例列表；client 是懒创建的，所以响应注入走 pending
    队列——_set_responses 可在首次发送（即首次建连）之前调用。
    """

    created: list[_FakeAsyncClient] = []
    _PENDING.clear()

    def _factory(*args: Any, **kwargs: Any) -> _FakeAsyncClient:
        client = _FakeAsyncClient(*args, **kwargs)
        if _PENDING:
            client.next_responses = _PENDING.pop(0)
        created.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    return created


_PENDING: list[list[_FakeResponse]] = []


def _set_responses(created: list[_FakeAsyncClient], responses: list[_FakeResponse]) -> None:
    if created:
        created[0].next_responses = list(responses)
    else:
        # client 尚未懒创建：预置给下一个创建的实例
        _PENDING.append(list(responses))


# ── 注册表完整性 ────────────────────────────────────────────────────────────

EXPECTED_OUTBOUND_TYPES = {
    "dingtalk",
    "wecom",
    "telegram",
    "slack",
    "discord",
    "ntfy",
    "bark",
    "gotify",
    "pushover",
    "serverchan",
    "pushplus",
}


def test_all_outbound_channels_discovered() -> None:
    channels = discover_all_channels()
    missing = EXPECTED_OUTBOUND_TYPES - set(channels)
    assert not missing, f"未注册的渠道: {missing}"
    assert "feishu" in channels  # 既有渠道不受影响


def test_channel_type_enum_matches_registry() -> None:
    for slug in EXPECTED_OUTBOUND_TYPES:
        assert ChannelType(slug) is not None


def test_notification_channels_keep_send_capability_and_chat_platforms_advertise_receiving() -> (
    None
):
    from src.infra.channel.registry import get_registry

    for slug in EXPECTED_OUTBOUND_TYPES:
        cls = get_registry().get_channel_class(ChannelType(slug))
        assert cls is not None
        caps = {c.value for c in cls.get_capabilities()}  # type: ignore[attr-defined]
        assert "send_message" in caps
        if slug in {"dingtalk", "wecom", "slack", "discord"}:
            assert "websocket" in caps
        elif slug == "telegram":
            assert "long_polling" in caps
        else:
            assert "websocket" not in caps
            assert "long_polling" not in caps
        # 前端动态表单依赖 config_fields
        assert cls.get_config_fields()  # type: ignore[attr-defined]


# ── 共享基类行为 ────────────────────────────────────────────────────────────


async def test_outbound_channel_reuses_http_client(fake_http) -> None:
    from src.infra.channel.ntfy import NtfyChannel, NtfyConfig

    channel = NtfyChannel(NtfyConfig(topic="lambchat", user_id="u1", instance_id="i1"))
    assert await channel.start() is True
    ok1 = await channel.send_message("", "hello world")
    ok2 = await channel.send_message("", "second message")
    assert ok1 and ok2
    assert len(fake_http) == 1  # 同实例共享连接
    assert len(fake_http[0].requests) == 2
    await channel.stop()
    assert fake_http[0].closed


async def test_send_failure_returns_false_and_recovers(fake_http) -> None:
    from src.infra.channel.ntfy import NtfyChannel, NtfyConfig

    channel = NtfyChannel(NtfyConfig(topic="t", user_id="u1", instance_id="i1"))
    await channel.start()
    _set_responses(fake_http, [_FakeResponse(status_code=503), _FakeResponse(status_code=200)])
    assert await channel.send_message("", "first") is False
    assert await channel.send_message("", "retry") is True
    await channel.stop()


async def test_long_content_is_truncated(fake_http) -> None:
    from src.infra.channel.discord import DiscordChannel, DiscordConfig

    channel = DiscordChannel(
        DiscordConfig(
            webhook_url="https://discord.com/api/webhooks/1/abc",
            user_id="u1",
            instance_id="i1",
        )
    )
    await channel.start()
    assert await channel.send_message("", "x" * 5000) is True
    sent = fake_http[0].requests[0]["json"]
    assert len(sent["content"]) <= DiscordChannel.max_content_chars  # type: ignore[attr-defined]
    await channel.stop()


# ── 各渠道 payload/端点 ─────────────────────────────────────────────────────


async def test_dingtalk_signed_markdown_message(fake_http) -> None:
    from src.infra.channel.dingtalk import DingTalkChannel, DingTalkConfig, build_signed_url

    signed = build_signed_url(
        "https://oapi.dingtalk.com/robot/send?access_token=abc",
        "SEC123",
        timestamp=1700000000000,
    )
    assert signed.startswith("https://oapi.dingtalk.com/robot/send?access_token=abc&")
    qs = parse_qs(urlsplit(signed).query)
    assert qs["timestamp"] == ["1700000000000"]
    assert qs["sign"]  # base64+urlencode 后非空

    channel = DingTalkChannel(
        DingTalkConfig(
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=abc",
            secret="SEC123",
            user_id="u1",
            instance_id="i1",
        )
    )
    await channel.start()
    _set_responses(fake_http, [_FakeResponse(json_data={"errcode": 0, "errmsg": "ok"})])
    assert await channel.send_message("", "## 任务完成\n结果如下") is True
    req = fake_http[0].requests[0]
    assert "oapi.dingtalk.com/robot/send" in req["url"]
    assert "sign=" in req["url"]
    assert req["json"] == {
        "msgtype": "markdown",
        "markdown": {"title": "任务完成", "text": "## 任务完成\n结果如下"},
    }
    await channel.stop()


async def test_dingtalk_reports_api_error(fake_http) -> None:
    from src.infra.channel.dingtalk import DingTalkChannel, DingTalkConfig

    channel = DingTalkChannel(
        DingTalkConfig(
            webhook_url="https://oapi.dingtalk.com/robot/send?access_token=bad",
            user_id="u1",
            instance_id="i1",
        )
    )
    await channel.start()
    _set_responses(
        fake_http, [_FakeResponse(json_data={"errcode": 310000, "errmsg": "sign not match"})]
    )
    assert await channel.send_message("", "hi") is False
    await channel.stop()


async def test_wecom_markdown_message(fake_http) -> None:
    from src.infra.channel.wecom import WeComChannel, WeComConfig

    channel = WeComChannel(
        WeComConfig(
            webhook_url="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=K1",
            user_id="u1",
            instance_id="i1",
        )
    )
    await channel.start()
    _set_responses(fake_http, [_FakeResponse(json_data={"errcode": 0, "errmsg": "ok"})])
    assert await channel.send_message("", "构建完成") is True
    req = fake_http[0].requests[0]
    assert req["url"].startswith("https://qyapi.weixin.qq.com/cgi-bin/webhook/send")
    assert req["json"]["msgtype"] == "markdown"
    assert "构建完成" in req["json"]["markdown"]["content"]
    await channel.stop()


async def test_telegram_chat_id_priority_and_payload(fake_http) -> None:
    from src.infra.channel.telegram import TelegramChannel, TelegramConfig

    channel = TelegramChannel(
        TelegramConfig(
            bot_token="123:ABC",
            default_chat_id="10086",
            user_id="u1",
            instance_id="i1",
        )
    )
    await channel.start()
    _set_responses(
        fake_http, [_FakeResponse(json_data={"ok": True}), _FakeResponse(json_data={"ok": True})]
    )
    # 显式 chat_id 优先，缺省回落 default_chat_id
    assert await channel.send_message("99999", "explicit") is True
    assert await channel.send_message("", "fallback") is True
    first, second = fake_http[0].requests[:2]
    assert first["url"] == "https://api.telegram.org/bot123:ABC/sendMessage"
    assert first["json"]["chat_id"] == "99999"
    assert first["json"]["text"] == "explicit"
    assert second["json"]["chat_id"] == "10086"
    await channel.stop()


async def test_telegram_reports_api_error(fake_http) -> None:
    from src.infra.channel.telegram import TelegramChannel, TelegramConfig

    channel = TelegramChannel(
        TelegramConfig(bot_token="123:ABC", default_chat_id="1", user_id="u1", instance_id="i1")
    )
    await channel.start()
    _set_responses(
        fake_http, [_FakeResponse(json_data={"ok": False, "description": " Unauthorized"})]
    )
    assert await channel.send_message("", "hi") is False
    await channel.stop()


async def test_slack_incoming_webhook(fake_http) -> None:
    from src.infra.channel.slack import SlackChannel, SlackConfig

    channel = SlackChannel(
        SlackConfig(
            webhook_url="https://hooks.slack.com/services/T1/B1/xxx",
            user_id="u1",
            instance_id="i1",
        )
    )
    await channel.start()
    assert await channel.send_message("", "deploy ok", title="LambChat") is True
    req = fake_http[0].requests[0]
    assert req["url"] == "https://hooks.slack.com/services/T1/B1/xxx"
    assert req["json"] == {"text": "deploy ok"}
    await channel.stop()


async def test_ntfy_topic_post_with_title(fake_http) -> None:
    from src.infra.channel.ntfy import NtfyChannel, NtfyConfig

    channel = NtfyChannel(NtfyConfig(topic="lambchat", user_id="u1", instance_id="i1"))
    await channel.start()
    assert await channel.send_message("", "backup done", title="Nightly") is True
    req = fake_http[0].requests[0]
    # JSON publish：URL 只到服务器根，topic/title/message 全在 body（中文标题兼容）
    assert req["url"] == "https://ntfy.sh"  # 默认公共服务器
    assert req["json"]["topic"] == "lambchat"
    assert req["json"]["title"] == "Nightly"
    assert req["json"]["message"] == "backup done"
    await channel.stop()


async def test_bark_push_payload(fake_http) -> None:
    from src.infra.channel.bark import BarkChannel, BarkConfig

    channel = BarkChannel(BarkConfig(device_key="DEVICEKEY", user_id="u1", instance_id="i1"))
    await channel.start()
    assert await channel.send_message("", "long job finished") is True
    req = fake_http[0].requests[0]
    assert req["url"] == "https://api.day.app/push"  # 默认服务器
    assert req["json"]["device_key"] == "DEVICEKEY"
    assert req["json"]["body"] == "long job finished"
    await channel.stop()


async def test_gotify_message_with_token_query(fake_http) -> None:
    from src.infra.channel.gotify import GotifyChannel, GotifyConfig

    channel = GotifyChannel(
        GotifyConfig(
            server="https://gotify.example.com", app_token="Atoken", user_id="u1", instance_id="i1"
        )
    )
    await channel.start()
    _set_responses(fake_http, [_FakeResponse(json_data={"id": 7})])
    assert await channel.send_message("", "runner done") is True
    req = fake_http[0].requests[0]
    assert req["url"].startswith("https://gotify.example.com/message")
    assert "token=Atoken" in req["url"]
    assert req["json"]["message"] == "runner done"
    await channel.stop()


async def test_pushover_form_payload(fake_http) -> None:
    from src.infra.channel.pushover import PushoverChannel, PushoverConfig

    channel = PushoverChannel(
        PushoverConfig(api_token="Akey", user_key="Ukey", user_id="u1", instance_id="i1")
    )
    await channel.start()
    _set_responses(fake_http, [_FakeResponse(json_data={"status": 1})])
    assert await channel.send_message("", "build ok", title="CI") is True
    req = fake_http[0].requests[0]
    assert req["url"] == "https://api.pushover.net/1/messages.json"
    assert req["data"]["token"] == "Akey"
    assert req["data"]["user"] == "Ukey"
    assert req["data"]["title"] == "CI"
    assert req["data"]["message"] == "build ok"
    await channel.stop()


async def test_serverchan_send_key_url(fake_http) -> None:
    from src.infra.channel.serverchan import ServerChanChannel, ServerChanConfig

    channel = ServerChanChannel(
        ServerChanConfig(send_key="SCT1234", user_id="u1", instance_id="i1")
    )
    await channel.start()
    _set_responses(fake_http, [_FakeResponse(json_data={"code": 0})])
    assert await channel.send_message("", "report ready") is True
    req = fake_http[0].requests[0]
    assert req["url"] == "https://sctapi.ftqq.com/SCT1234.send"
    assert req["data"]["desp"] == "report ready"
    _set_responses(fake_http, [_FakeResponse(json_data={"code": 1, "message": "bad key"})])
    assert await channel.send_message("", "again") is False
    await channel.stop()


async def test_pushplus_payload(fake_http) -> None:
    from src.infra.channel.pushplus import PushPlusChannel, PushPlusConfig

    channel = PushPlusChannel(PushPlusConfig(token="PPtoken", user_id="u1", instance_id="i1"))
    await channel.start()
    _set_responses(fake_http, [_FakeResponse(json_data={"code": 200})])
    assert await channel.send_message("", "digest", title="日报") is True
    req = fake_http[0].requests[0]
    assert req["url"] == "https://www.pushplus.plus/send"
    assert req["json"]["token"] == "PPtoken"
    assert req["json"]["title"] == "日报"
    assert req["json"]["content"] == "digest"
    await channel.stop()


# ── Manager 生命周期 ────────────────────────────────────────────────────────


class _FakeStorage:
    """替代 ChannelStorage：预置配置 dict，iter/list 直读内存。"""

    def __init__(self, configs: list[dict[str, Any]]):
        self.configs = configs

    async def iter_enabled_configs(self, channel_type: Any):
        for cfg in self.configs:
            if cfg.get("channel_type") == channel_type.value and cfg.get("enabled", True):
                yield cfg

    async def list_user_configs_by_type(self, user_id: str, channel_type: Any) -> list[dict]:
        return [
            cfg
            for cfg in self.configs
            if cfg.get("user_id") == user_id and cfg.get("channel_type") == channel_type.value
        ]


async def test_outbound_manager_starts_and_reloads(fake_http) -> None:
    from src.infra.channel.ntfy import NtfyChannelManager

    storage = _FakeStorage(
        [
            {
                "user_id": "u1",
                "channel_type": "ntfy",
                "instance_id": "inst-1",
                "name": "my ntfy",
                "enabled": True,
                "topic": "lambchat",
            },
            {
                "user_id": "u2",
                "channel_type": "ntfy",
                "instance_id": "inst-2",
                "name": "disabled one",
                "enabled": False,
                "topic": "other",
            },
        ]
    )
    manager = NtfyChannelManager()
    manager._storage = storage  # noqa: SLF001
    await manager.start()

    channel = manager.get_channel("u1", "inst-1")
    assert channel is not None and channel.is_running
    assert manager.get_channel("u2") is None  # disabled 未启动
    assert manager.is_connected("u1", "inst-1") is True

    # reload_user 重建实例
    storage.configs[0]["topic"] = "renamed"
    assert await manager.reload_user("u1", "inst-1") is True
    channel = manager.get_channel("u1", "inst-1")
    assert channel is not None and getattr(channel.config, "topic") == "renamed"

    await manager.stop()
    assert manager.get_channel("u1", "inst-1") is None


async def test_coordinator_delivers_to_outbound_channel(fake_http) -> None:
    from src.infra.channel.manager import ChannelCoordinator
    from src.infra.channel.ntfy import NtfyChannelManager
    from src.kernel.schemas import channel as channel_schemas

    storage = _FakeStorage(
        [
            {
                "user_id": "u1",
                "channel_type": "ntfy",
                "instance_id": "inst-1",
                "name": "n",
                "enabled": True,
                "topic": "lambchat",
            }
        ]
    )
    manager = NtfyChannelManager()
    manager._storage = storage  # noqa: SLF001
    await manager.start()

    coordinator = ChannelCoordinator()
    coordinator._managers[channel_schemas.ChannelType.NTFY] = manager  # noqa: SLF001
    assert (
        await coordinator.send_message(
            "u1", channel_schemas.ChannelType.NTFY, "", "task finished", instance_id="inst-1"
        )
        is True
    )
    assert fake_http[0].requests[0]["url"] == "https://ntfy.sh"
    await manager.stop()


async def test_coordinator_lazily_resolves_started_manager_singleton(fake_http) -> None:
    """coordinator.start() 未被调用的部署路径（main.py 专用启动链路）下，
    send_message 应惰性复用已被启动的 manager 单例（定时任务投递链路）。"""
    from src.infra.channel.manager import ChannelCoordinator
    from src.infra.channel.ntfy import NtfyChannelManager
    from src.kernel.schemas import channel as channel_schemas

    storage = _FakeStorage(
        [
            {
                "user_id": "u1",
                "channel_type": "ntfy",
                "instance_id": "inst-lazy",
                "name": "n",
                "enabled": True,
                "topic": "lambchat",
            }
        ]
    )
    # 模拟 start_outbound_channels 的效果：manager 单例已启动，但未注册进 coordinator
    singleton = NtfyChannelManager.get_instance()
    singleton._storage = storage  # noqa: SLF001
    await singleton.start()
    try:
        coordinator = ChannelCoordinator()  # 空 _managers，未 start()
        assert (
            await coordinator.send_message(
                "u1", channel_schemas.ChannelType.NTFY, "", "hello", instance_id="inst-lazy"
            )
            is True
        )
        assert fake_http[0].requests[0]["url"] == "https://ntfy.sh"
    finally:
        await singleton.stop()
        # 清理单例缓存，避免污染其他测试
        from src.infra.channel.base import UserChannelManager

        UserChannelManager._instances.pop(NtfyChannelManager, None)  # noqa: SLF001
