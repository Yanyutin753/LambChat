"""微信 iLink Bot 渠道测试。

协议对齐 zcode 开源实现（packages/services/src/bots/providers/weixinProvider.ts）：
Bearer ilink_bot_token + 随机 X-WECHAT-UIN 头、/getupdates 长轮询（buf 游标，
处理完才持久化）、/sendmessage 发文本（item_list + CRLF）、扫码注册轮询。
"""

import asyncio
import base64
from typing import Any

import httpx
import pytest

import src.infra.channel  # noqa: F401  预热渠道包：飞书 sender 类体在 patch httpx 前完成定义
from src.kernel.schemas.channel import ChannelType

# ── fakes ───────────────────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, status_code: int = 200, json_data: Any = None):
        self.status_code = status_code
        self._json = json_data

    @property
    def is_error(self) -> bool:
        return self.status_code >= 400

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json


class _FakeAsyncClient:
    def __init__(self, *args: Any, **kwargs: Any):
        self.requests: list[dict[str, Any]] = []
        self.next_responses: list[_FakeResponse] = [_FakeResponse()]
        self.closed = False

    @property
    def is_closed(self) -> bool:
        return self.closed

    async def post(self, url: str, *, json: Any = None, headers: Any = None, **kw: Any):
        self.requests.append({"method": "POST", "url": url, "json": json, "headers": headers})
        return self.next_responses.pop(0) if self.next_responses else _FakeResponse()

    async def get(self, url: str, *, headers: Any = None, **kw: Any):
        self.requests.append({"method": "GET", "url": url, "headers": headers})
        return self.next_responses.pop(0) if self.next_responses else _FakeResponse()

    async def aclose(self):
        pass


@pytest.fixture()
def fake_http(monkeypatch):
    created: list[_FakeAsyncClient] = []

    def _factory(*args: Any, **kwargs: Any) -> _FakeAsyncClient:
        client = _FakeAsyncClient(*args, **kwargs)
        if _PENDING:
            client.next_responses = _PENDING.pop(0)
        created.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    _PENDING.clear()
    return created


_PENDING: list[list[_FakeResponse]] = []


def _respond(created: list[_FakeAsyncClient], responses: list[_FakeResponse]) -> None:
    if created:
        created[0].next_responses = list(responses)
    else:
        _PENDING.append(list(responses))


# ── 注册表/枚举 ─────────────────────────────────────────────────────────────


def test_weixin_registered_as_bidirectional_channel() -> None:
    from src.infra.channel.registry import discover_all_channels, get_registry

    channels = discover_all_channels()
    assert "weixin" in channels
    cls = get_registry().get_channel_class(ChannelType.WEIXIN)
    assert cls is not None
    caps = {c.value for c in cls.get_capabilities()}
    assert "long_polling" in caps
    assert "send_message" in caps


# ── provider 协议层 ─────────────────────────────────────────────────────────


def test_build_request_headers() -> None:
    from src.infra.channel.weixin.provider import build_request_headers

    headers = build_request_headers("TOKEN123")
    assert headers["AuthorizationType"] == "ilink_bot_token"
    assert headers["Authorization"] == "Bearer TOKEN123"
    assert headers["content-type"] == "application/json"
    # X-WECHAT-UIN 是随机 uint32 的 base64
    uin = base64.b64decode(headers["X-WECHAT-UIN"]).decode()
    assert 0 <= int(uin) < 2**32


async def test_get_updates_parses_messages_and_buf(fake_http) -> None:
    from src.infra.channel.weixin.provider import get_updates

    client = _FakeAsyncClient()
    client.next_responses = [
        _FakeResponse(
            json_data={
                "ret": 0,
                "data": {
                    "get_updates_buf": "NEXTBUF",
                    "msgs": [
                        # 正常私聊文本
                        {
                            "message_type": 0,
                            "from_user_id": "wxid_alice",
                            "id": "m1",
                            "msg": {
                                "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
                            },
                            "context_token": "ctx-1",
                        },
                        # 自己发的 bot 消息（message_type==2）必须跳过
                        {"message_type": 2, "from_user_id": "wxid_me", "id": "m2"},
                        # 群聊消息带 room
                        {
                            "message_type": 0,
                            "from_user_id": "wxid_bob",
                            "room": "room-9",
                            "id": "m3",
                            "msg": {
                                "item_list": [
                                    {"type": 1, "text_item": {"text": "hi "}},
                                    {"type": 1, "text_item": {"text": "team"}},
                                ],
                            },
                        },
                    ],
                },
            }
        )
    ]
    messages, next_buf = await get_updates(client, "TOKEN", "PREVBUF")

    req = client.requests[0]
    assert req["url"] == "https://ilinkai.weixin.qq.com/ilink/bot/getupdates"
    assert req["json"]["get_updates_buf"] == "PREVBUF"
    assert req["json"]["base_info"] == {"channel_version": "2.0.0"}

    assert next_buf == "NEXTBUF"
    assert len(messages) == 2
    first = messages[0]
    assert first["sender_id"] == "wxid_alice"
    assert first["chat_id"] == "wxid_alice"  # 私聊无 room → chat_id=发送者
    assert first["content"] == "hello"
    assert first["context_token"] == "ctx-1"
    assert first["message_id"] == "m1"
    second = messages[1]
    assert second["chat_id"] == "room-9"  # 群聊 → chat_id=room
    assert second["content"] == "hi \nteam"  # item_list 文本按行聚合


async def test_get_updates_rejects_api_error(fake_http) -> None:
    from src.infra.channel.weixin.provider import get_updates

    client = _FakeAsyncClient()
    client.next_responses = [_FakeResponse(json_data={"errcode": 40001, "errmsg": "bad token"})]
    with pytest.raises(Exception, match="40001|bad token"):
        await get_updates(client, "TOKEN", "")


async def test_send_bot_message_payload(fake_http) -> None:
    from src.infra.channel.weixin.provider import send_bot_message

    client = _FakeAsyncClient()
    client.next_responses = [_FakeResponse(json_data={"ret": 0})]
    ok = await send_bot_message(client, "TOKEN", to_user_id="wxid_alice", text="第一行\n第二行")
    assert ok is True
    req = client.requests[0]
    assert req["url"] == "https://ilinkai.weixin.qq.com/ilink/bot/sendmessage"
    msg = req["json"]["msg"]
    assert msg["to_user_id"] == "wxid_alice"
    assert msg["message_type"] == 2
    assert msg["message_state"] == 2
    assert msg["item_list"] == [
        {"type": 1, "text_item": {"text": "第一行\r\n第二行"}}  # LF 统一为 CRLF
    ]
    assert "context_token" not in msg


async def test_send_bot_message_with_context_token(fake_http) -> None:
    from src.infra.channel.weixin.provider import send_bot_message

    client = _FakeAsyncClient()
    client.next_responses = [_FakeResponse(json_data={"ret": 0})]
    assert (
        await send_bot_message(client, "TOKEN", to_user_id="u1", text="x", context_token="ctx-9")
        is True
    )
    assert client.requests[0]["json"]["msg"]["context_token"] == "ctx-9"


async def test_qr_registration_begin_and_poll(fake_http) -> None:
    from src.infra.channel.weixin.provider import begin_qr_registration, poll_qr_registration

    client = _FakeAsyncClient()
    client.next_responses = [
        _FakeResponse(
            json_data={"ret": 0, "qrcode": "QR1", "qrcode_img_content": "https://qr/x.png"}
        ),
        _FakeResponse(json_data={"ret": 0, "status": 1}),
        _FakeResponse(json_data={"ret": 0, "status": 2, "bot_token": "BOT-TOKEN"}),
    ]
    session = await begin_qr_registration(client)
    assert session["qr_code"] == "QR1"
    assert session["qr_url"] == "https://qr/x.png"
    assert client.requests[0]["url"].endswith("/get_bot_qrcode?bot_type=3")

    pending = await poll_qr_registration(client, "QR1")
    assert pending["status"] == "scanned"
    success = await poll_qr_registration(client, "QR1")
    assert success["status"] == "success"
    assert success["bot_token"] == "BOT-TOKEN"


# ── WeixinChannel ───────────────────────────────────────────────────────────


def _weixin_config(**overrides: Any) -> Any:
    from src.kernel.schemas.weixin import WeixinConfig

    defaults: dict[str, Any] = {
        "user_id": "u1",
        "instance_id": "i1",
        "bot_token": "TOKEN",
        "enabled": True,
    }
    defaults.update(overrides)
    return WeixinConfig(**defaults)


class _FakeRedisStorage:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[str] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, **kwargs: Any) -> None:
        self.values[key] = value
        self.set_calls.append(key)

    async def set_nx(self, key: str, value: str, ttl: int = 30) -> bool:
        if key in self.values:
            return False
        self.values[key] = value
        return True

    async def expire(self, key: str, ttl: int) -> None:
        pass

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


async def test_channel_dispatches_inbound_messages(fake_http, monkeypatch) -> None:
    from src.infra.channel.weixin.channel import WeixinChannel

    received: list[dict[str, Any]] = []

    async def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    channel = WeixinChannel(_weixin_config(), message_handler=handler)
    fake_redis = _FakeRedisStorage()

    async def fake_get_updates(client: Any, token: str, buf: str) -> tuple[list, str]:
        return (
            [
                {
                    "sender_id": "wxid_alice",
                    "chat_id": "wxid_alice",
                    "content": "你好",
                    "context_token": "ctx-1",
                    "message_id": "m1",
                    "display_name": "Alice",
                }
            ],
            "BUF2",
        )

    monkeypatch.setattr("src.infra.channel.weixin.provider.get_updates", fake_get_updates)

    async def _always_first(key: str, ttl: int = 3600) -> bool:
        return True

    monkeypatch.setattr("src.infra.channel.weixin.channel._mark_message_seen", _always_first)
    await channel._consume_once(fake_redis)  # noqa: SLF001

    assert len(received) == 1
    msg = received[0]
    assert msg["sender_id"] == "wxid_alice"
    assert msg["content"] == "你好"
    assert msg["chat_id"] == "wxid_alice"
    assert msg["metadata"]["context_token"] == "ctx-1"
    assert msg["metadata"]["instance_id"] == "i1"
    # 游标在消息处理完之后才持久化
    assert fake_redis.values["weixin:buf:u1:i1"] == "BUF2"


async def test_channel_group_policy_off_ignores_group_messages(monkeypatch) -> None:
    from src.infra.channel.weixin.channel import WeixinChannel

    received: list[dict[str, Any]] = []

    async def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    channel = WeixinChannel(_weixin_config(group_policy="off"), message_handler=handler)
    fake_redis = _FakeRedisStorage()

    async def fake_get_updates(client: Any, token: str, buf: str) -> tuple[list, str]:
        return (
            [
                {
                    "sender_id": "wxid_bob",
                    "chat_id": "room-9",
                    "content": "群里喊一嗓子",
                    "context_token": None,
                    "message_id": "m3",
                }
            ],
            "BUF",
        )

    monkeypatch.setattr("src.infra.channel.weixin.provider.get_updates", fake_get_updates)

    async def _always_first(key: str, ttl: int = 3600) -> bool:
        return True

    monkeypatch.setattr("src.infra.channel.weixin.channel._mark_message_seen", _always_first)
    await channel._consume_once(fake_redis)  # noqa: SLF001
    assert received == []  # 群聊被过滤


async def test_channel_send_message_uses_default_chat_id(fake_http) -> None:
    from src.infra.channel.weixin.channel import WeixinChannel

    _respond(fake_http, [_FakeResponse(json_data={"ret": 0}), _FakeResponse(json_data={"ret": 0})])
    channel = WeixinChannel(_weixin_config(default_chat_id="wxid_owner"))
    assert await channel.send_message("", "任务完成") is True
    req = fake_http[0].requests[0]
    assert req["json"]["msg"]["to_user_id"] == "wxid_owner"

    # 显式 chat_id 优先
    assert await channel.send_message("room-9", "群里通知") is True
    assert fake_http[0].requests[1]["json"]["msg"]["to_user_id"] == "room-9"


# ── 结果文本提取（proactive 投递复用） ─────────────────────────────────────


def test_extract_channel_delivery_text() -> None:
    from src.infra.channel.delivery import extract_delivery_text

    events = [
        {"event_type": "thinking", "data": {"content": "internal"}},
        {"event_type": "message:chunk", "data": {"content": "答案是 "}},
        {"event_type": "tool:start", "data": {"tool": "search"}},
        {"event_type": "message:chunk", "data": {"content": "42"}},
    ]
    assert extract_delivery_text(events) == "答案是 42"
    assert extract_delivery_text([]) == ""
    assert extract_delivery_text(events, max_chars=5) == "答案是 4"


# ── 任务通知渠道兜底（proactive 基础） ──────────────────────────────────────


class _FakeCoordinator:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_message(self, user_id, channel_type, chat_id, content, instance_id=None):
        self.sent.append(
            {
                "user_id": user_id,
                "channel_type": getattr(channel_type, "value", channel_type),
                "chat_id": chat_id,
                "content": content,
                "instance_id": instance_id,
            }
        )
        return True


class _FakeChannelStorage:
    def __init__(self, configs: list[dict[str, Any]]) -> None:
        self.configs = configs

    async def list_user_configs(self, user_id: str) -> list[dict[str, Any]]:
        return self.configs


class _FakeSessionObj:
    def __init__(self, metadata: dict[str, Any] | None) -> None:
        self.metadata = metadata


class _FakeSessionManagerForFallback:
    def __init__(self, session: Any) -> None:
        self._session = session

    async def get_session(self, session_id: str):
        return self._session


class _FakeTraceStorage:
    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events

    async def get_run_events(self, session_id: str, run_id: str):
        return self._events


async def test_fallback_delivers_agent_text_when_user_offline(monkeypatch) -> None:
    from src.infra.channel import fallback

    coordinator = _FakeCoordinator()
    monkeypatch.setattr("src.infra.channel.manager.get_channel_coordinator", lambda: coordinator)
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: _FakeSessionManagerForFallback(_FakeSessionObj(metadata=None)),
    )
    monkeypatch.setattr(
        "src.infra.channel.channel_storage.ChannelStorage",
        lambda: _FakeChannelStorage(
            [
                {
                    "user_id": "u1",
                    "channel_type": "ntfy",
                    "instance_id": "inst-1",
                    "enabled": True,
                    "default_chat_id": "my-topic",
                    "topic": "my-topic",
                }
            ]
        ),
    )
    monkeypatch.setattr(
        "src.infra.session.trace_storage.get_trace_storage",
        lambda: _FakeTraceStorage(
            [{"event_type": "message:chunk", "data": {"content": "跑完了，共 3 个文件"}}]
        ),
    )

    ok = await fallback.deliver_task_fallback(
        user_id="u1",
        session_id="s1",
        run_id="r1",
        status_value="completed",
        message=None,
    )
    assert ok is True
    assert len(coordinator.sent) == 1
    sent = coordinator.sent[0]
    assert sent["channel_type"] == "ntfy"
    assert sent["instance_id"] == "inst-1"
    assert "任务完成" in sent["content"]
    assert "跑完了，共 3 个文件" in sent["content"]


async def test_fallback_skips_channel_originated_sessions(monkeypatch) -> None:
    from src.infra.channel import fallback

    coordinator = _FakeCoordinator()
    monkeypatch.setattr("src.infra.channel.manager.get_channel_coordinator", lambda: coordinator)
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: _FakeSessionManagerForFallback(
            _FakeSessionObj(
                metadata={"channel_delivery": {"channel_type": "weixin", "chat_id": "wx"}}
            )
        ),
    )
    ok = await fallback.deliver_task_fallback(
        user_id="u1", session_id="s1", run_id="r1", status_value="completed", message="done"
    )
    assert ok is False
    assert coordinator.sent == []


async def test_fallback_ignores_non_terminal_status(monkeypatch) -> None:
    from src.infra.channel import fallback

    ok = await fallback.deliver_task_fallback(
        user_id="u1", session_id="s1", run_id="r1", status_value="waiting_human", message=None
    )
    assert ok is False


# ── 微信 handler：事件流 → 文本回复 ───────────────────────────────────────


async def test_weixin_event_processing_replies_full_text(monkeypatch) -> None:
    from src.infra.channel.weixin.handler import _process_events_and_reply

    replies: list[str] = []

    async def send(text: str) -> None:
        replies.append(text)

    class _FakeDualWriter:
        async def read_from_redis(self, session_id, run_id):
            for event in (
                {"event_type": "message:chunk", "data": {"content": "你"}},
                {"event_type": "message:chunk", "data": {"content": "好"}},
                {"event_type": "done", "data": {}},
            ):
                yield event

    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: _FakeDualWriter())
    await _process_events_and_reply(send, "s1", "r1")
    assert replies == ["你好"]


async def test_weixin_event_processing_handles_approval(monkeypatch) -> None:
    from src.infra.channel.weixin.handler import APPROVAL_HINT, _process_events_and_reply

    replies: list[str] = []

    async def send(text: str) -> None:
        replies.append(text)

    class _FakeDualWriter:
        async def read_from_redis(self, session_id, run_id):
            yield {"event_type": "approval_required", "data": {"id": "ap1"}}
            yield {"event_type": "message:chunk", "data": {"content": "部分结果"}}
            yield {"event_type": "done", "data": {}}

    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: _FakeDualWriter())
    await _process_events_and_reply(send, "s1", "r1")
    assert replies[0] == APPROVAL_HINT
    assert replies[1] == "部分结果"


# ── review 修复钉子 ─────────────────────────────────────────────────────────


def test_weixin_manager_get_instance_returns_global_singleton() -> None:
    """P0：路由/pubsub/coordinator 走 get_instance()，必须复用带 handler 的全局单例。"""
    from src.infra.channel.weixin.manager import WeixinChannelManager, get_weixin_channel_manager

    assert WeixinChannelManager.get_instance() is get_weixin_channel_manager()


async def test_outbound_reload_user_stops_disabled_instance() -> None:
    """P1：disable/delete 靠 reload_user 停止运行中实例（先停再按需重启）。"""
    from src.infra.channel.ntfy import NtfyChannelManager
    from tests.infra.test_outbound_channels import _FakeStorage  # noqa: PLC0415

    storage = _FakeStorage(
        [
            {
                "user_id": "u1",
                "channel_type": "ntfy",
                "instance_id": "inst-1",
                "name": "n",
                "enabled": True,
                "topic": "t",
            }
        ]
    )
    manager = NtfyChannelManager()
    manager._storage = storage  # noqa: SLF001
    await manager.start()
    assert manager.get_channel("u1", "inst-1") is not None

    # disable：配置标记 enabled=False 后 reload，实例必须被停止
    storage.configs[0]["enabled"] = False
    assert await manager.reload_user("u1", "inst-1") is True
    assert manager.get_channel("u1", "inst-1") is None


# ── 双消费修复钉子（2026-10-05 生产事故：一条消息被双 Pod 各跑一个 run） ────


class _FakeRedisClient:
    """锁/去重走 get_redis_client() 的最小替身（set nx / get / expire / delete）。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.set_calls: list[dict[str, Any]] = []
        self.expire_calls: list[tuple[str, int]] = []
        self.deleted: list[str] = []

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        self.set_calls.append({"key": key, "value": value, "nx": nx, "ex": ex})
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def get(self, key: str):
        return self.store.get(key)

    async def expire(self, key: str, ttl: int):
        self.expire_calls.append((key, int(ttl)))
        return True

    async def delete(self, *keys: str):
        self.deleted.extend(keys)
        for key in keys:
            self.store.pop(key, None)

    async def eval(self, script, numkeys, key, owner, *args):
        if self.store.get(key) != owner:
            return 0
        if args:
            await self.expire(key, args[0])
        else:
            await self.delete(key)
        return 1


def _inbound_payload(text: str, *, message_id: str | None = None) -> _FakeResponse:
    msg: dict[str, Any] = {
        "message_type": 0,
        "from_user_id": "wxid_alice",
        "msg": {"item_list": [{"type": 1, "text_item": {"text": text}}]},
    }
    if message_id:
        msg["id"] = message_id
    return _FakeResponse(json_data={"ret": 0, "data": {"get_updates_buf": "BUF2", "msgs": [msg]}})


async def test_consume_once_dedups_same_batch_delivery_without_message_id(
    fake_http, monkeypatch
) -> None:
    """iLink 消息体无 id 字段时，同一批次的同一条消息仍需去重。"""
    import src.infra.storage.redis as redis_mod
    from src.infra.channel.weixin.channel import SEEN_FINGERPRINT_TTL_SECONDS, WeixinChannel

    received: list[dict[str, Any]] = []

    async def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    channel = WeixinChannel(_weixin_config(), message_handler=handler)
    # 同一条消息被两个消费方各拉到一次（生产事故复现）
    _respond(fake_http, [_inbound_payload("你能干啥"), _inbound_payload("你能干啥")])

    fake_storage = _FakeRedisStorage()
    monkeypatch.setattr(redis_mod, "RedisStorage", lambda: fake_storage)
    fake_client = _FakeRedisClient()
    monkeypatch.setattr(redis_mod, "get_redis_client", lambda: fake_client)

    await channel._consume_once(fake_storage)  # noqa: SLF001
    await channel._consume_once(fake_storage)  # noqa: SLF001
    assert len(received) == 1  # 第二次必须被指纹去重挡下

    fp_keys = [k for k in fake_client.store if k.startswith("weixin:seen:u1:i1:fp:")]
    assert len(fp_keys) == 1  # 同指纹只落一个去重键
    fp_calls = [c for c in fake_client.set_calls if c["key"].startswith("weixin:seen:u1:i1:fp:")]
    assert fp_calls[0]["ex"] == SEEN_FINGERPRINT_TTL_SECONDS  # 短窗兜底，不误吞连发重复
    assert fp_calls[1]["nx"] is True  # 第二次仍走 NX（返回 False 被挡下）


async def test_consume_once_dedup_by_message_id_keeps_long_ttl(fake_http, monkeypatch) -> None:
    """有 message_id 时保持原长 TTL 去重（钉住既有行为）。"""
    import src.infra.storage.redis as redis_mod
    from src.infra.channel.weixin.channel import SEEN_MESSAGE_TTL_SECONDS, WeixinChannel

    received: list[dict[str, Any]] = []

    async def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    channel = WeixinChannel(_weixin_config(), message_handler=handler)
    _respond(fake_http, [_inbound_payload("你好", message_id="m1")])

    fake_storage = _FakeRedisStorage()
    monkeypatch.setattr(redis_mod, "RedisStorage", lambda: fake_storage)
    fake_client = _FakeRedisClient()
    monkeypatch.setattr(redis_mod, "get_redis_client", lambda: fake_client)

    await channel._consume_once(fake_storage)  # noqa: SLF001
    assert len(received) == 1
    id_sets = [c for c in fake_client.set_calls if c["key"] == "weixin:seen:u1:i1:id:m1"]
    assert len(id_sets) == 1
    assert id_sets[0]["ex"] == SEEN_MESSAGE_TTL_SECONDS


async def test_renew_poll_lock_only_renews_own_lock() -> None:
    """续期必须校验 owner：锁被他人夺走后不得给他人的锁续命。"""
    from src.infra.channel.weixin import channel as ch

    client = _FakeRedisClient()
    client.store["weixin:poll-lock:u1:i1"] = "OWNER-B"
    assert await ch._renew_poll_lock("u1", "i1", "OWNER-A", client=client) is False
    assert client.expire_calls == []

    client.store["weixin:poll-lock:u1:i1"] = "OWNER-A"
    assert await ch._renew_poll_lock("u1", "i1", "OWNER-A", client=client) is True
    assert client.expire_calls == [("weixin:poll-lock:u1:i1", ch.POLL_LOCK_TTL_SECONDS)]


async def test_release_poll_lock_keeps_foreign_lock() -> None:
    """释放必须校验 owner：不得误删其他消费者的锁。"""
    from src.infra.channel.weixin import channel as ch

    client = _FakeRedisClient()
    client.store["weixin:poll-lock:u1:i1"] = "OWNER-B"
    await ch._release_poll_lock("u1", "i1", "OWNER-A", client=client)
    assert client.store.get("weixin:poll-lock:u1:i1") == "OWNER-B"

    await ch._release_poll_lock("u1", "i1", "OWNER-B", client=client)
    assert "weixin:poll-lock:u1:i1" not in client.store


async def test_poll_loop_renews_each_round_and_yields_when_lock_lost(
    fake_http, monkeypatch
) -> None:
    """每轮长轮询前续期；锁丢失立即让位，不再发起长轮询（防双消费）。"""
    import src.infra.channel.weixin.channel as ch
    import src.infra.storage.redis as redis_mod

    received: list[dict[str, Any]] = []

    async def handler(**kwargs: Any) -> None:
        received.append(kwargs)

    channel = ch.WeixinChannel(_weixin_config(), message_handler=handler)
    _respond(fake_http, [_inbound_payload("你能干啥")])

    fake_storage = _FakeRedisStorage()
    monkeypatch.setattr(redis_mod, "RedisStorage", lambda: fake_storage)
    monkeypatch.setattr(redis_mod, "get_redis_client", lambda: _FakeRedisClient())

    holders: list[str] = []

    async def fake_acquire(uid: str, iid: str, owner: str) -> bool:
        if holders:
            return False  # 让位后不再抢锁，停在 standby
        holders.append(owner)
        return True

    renew_seq = [True, False]

    async def fake_renew(uid: str, iid: str, owner: str) -> bool:
        assert owner == holders[0]
        if not renew_seq:
            return False
        return renew_seq.pop(0)

    releases: list[str] = []

    async def fake_release(uid: str, iid: str, owner: str) -> None:
        releases.append(owner)

    monkeypatch.setattr(ch, "_acquire_poll_lock", fake_acquire)
    monkeypatch.setattr(ch, "_renew_poll_lock", fake_renew)
    monkeypatch.setattr(ch, "_release_poll_lock", fake_release)
    monkeypatch.setattr(ch, "POLL_LOCK_RETRY_SECONDS", 0)

    channel._running = True  # noqa: SLF001
    task = asyncio.create_task(channel._poll_loop())  # noqa: SLF001
    await asyncio.sleep(0.2)
    channel._running = False  # noqa: SLF001
    await asyncio.wait_for(task, timeout=2)

    assert len(received) == 1  # 消息只消费一次
    # 锁丢失后立即让位：只发起过一次 getupdates 长轮询
    assert len(fake_http[0].requests) == 1
    assert releases == [holders[0]]  # 释放的是自己的 owner


async def test_identical_text_in_distinct_update_batches_is_not_lost(fake_http, monkeypatch):
    import src.infra.storage.redis as redis_mod
    from src.infra.channel.weixin.channel import WeixinChannel

    received = []

    async def handler(**kwargs):
        received.append(kwargs)

    channel = WeixinChannel(_weixin_config(), message_handler=handler)
    first = _inbound_payload("继续")
    second = _inbound_payload("继续")
    second._json["data"]["get_updates_buf"] = "BUF3"
    _respond(fake_http, [first, second])
    client = _FakeRedisClient()
    monkeypatch.setattr(redis_mod, "get_redis_client", lambda: client)
    storage = _FakeRedisStorage()
    await channel._consume_once(storage)
    await channel._consume_once(storage)
    assert len(received) == 2


async def test_identical_messages_in_different_instances_do_not_collide(fake_http, monkeypatch):
    import src.infra.storage.redis as redis_mod
    from src.infra.channel.weixin.channel import WeixinChannel

    received = []

    async def handler(**kwargs):
        received.append(kwargs)

    client = _FakeRedisClient()
    monkeypatch.setattr(redis_mod, "get_redis_client", lambda: client)
    for instance in ("instance-a", "instance-b"):
        config = _weixin_config().model_copy(update={"instance_id": instance})
        channel = WeixinChannel(config, message_handler=handler)
        _PENDING.append([_inbound_payload("你好", message_id="same-id")])
        await channel._consume_once(_FakeRedisStorage())
    assert len(received) == 2


@pytest.mark.parametrize("operation", ["renew", "release"])
async def test_poll_lock_owner_change_cannot_affect_new_owner(operation):
    from src.infra.channel.weixin import channel as ch

    class ChangedOwnerRedis(_FakeRedisClient):
        async def get(self, key):
            old = await super().get(key)
            self.store[key] = "NEW-OWNER"
            return old

        async def eval(self, *args):
            self.store["weixin:poll-lock:u1:i1"] = "NEW-OWNER"
            return await super().eval(*args)

    client = ChangedOwnerRedis()
    key = "weixin:poll-lock:u1:i1"
    client.store[key] = "OLD-OWNER"
    if operation == "renew":
        assert not await ch._renew_poll_lock("u1", "i1", "OLD-OWNER", client=client)
        assert client.expire_calls == []
    else:
        await ch._release_poll_lock("u1", "i1", "OLD-OWNER", client=client)
    assert client.store[key] == "NEW-OWNER"


def test_no_id_delivery_identity_distinguishes_batch_positions_and_context():
    from src.infra.channel.weixin.channel import _dedup_key

    message = {"chat_id": "a", "sender_id": "a", "content": "继续"}
    assert _dedup_key(message, "batch", 0) != _dedup_key(message, "batch", 1)
    assert _dedup_key(message, "batch", 0) != _dedup_key(
        {**message, "context_token": "new"}, "batch", 0
    )
    assert _dedup_key(message, None, 0) is None
