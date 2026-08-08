from __future__ import annotations

import asyncio
import json
import logging
import threading
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from src.infra.channel.feishu.channel import FeishuChannel
from src.kernel.schemas.feishu import FeishuConfig, FeishuGroupPolicy


class _FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True


def _build_channel(user_id: str = "user-1") -> FeishuChannel:
    return FeishuChannel(
        FeishuConfig(
            user_id=user_id,
            instance_id="instance-1",
            app_id="app-id",
            app_secret="app-secret",
            encrypt_key="",
            verification_token="",
            react_emoji="THUMBSUP",
            group_policy=FeishuGroupPolicy.MENTION,
            enabled=True,
        )
    )


def _build_message_event(
    *,
    message_type: str,
    content: str,
    chat_type: str = "p2p",
):
    message = SimpleNamespace(
        message_id="om_1",
        content=content,
        chat_id="oc_chat",
        chat_type=chat_type,
        message_type=message_type,
        root_id=None,
        mentions=[],
    )
    sender = SimpleNamespace(
        sender_type="user",
        sender_id=SimpleNamespace(open_id="ou_sender"),
    )
    return SimpleNamespace(event=SimpleNamespace(message=message, sender=sender))


def _build_card_action_event(value: Any):
    action = SimpleNamespace(value=value)
    context = SimpleNamespace(open_message_id="om_card", open_chat_id="oc_chat")
    return SimpleNamespace(event=SimpleNamespace(action=action, context=context))


def _build_fake_lark_module() -> ModuleType:
    module = ModuleType("lark_oapi")

    class _FakeBuilder:
        def app_id(self, _value: str):
            return self

        def app_secret(self, _value: str):
            return self

        def log_level(self, _value):
            return self

        def build(self):
            return object()

    class _FakeClientFactory:
        @staticmethod
        def builder():
            return _FakeBuilder()

    class _FakeEventHandlerBuilder:
        def register_p2_im_message_receive_v1(self, _handler):
            return self

        def build(self):
            return object()

    class _FakeEventDispatcherHandler:
        @staticmethod
        def builder(_encrypt_key: str, _verification_token: str):
            return _FakeEventHandlerBuilder()

    class _FakeWsClient:
        def __init__(self, *args, **kwargs):
            self._reconnect_interval = None
            self._reconnect_nonce = None

    class _FakeWsNamespace:
        Client = _FakeWsClient

    class _FakeLogLevel:
        INFO = "INFO"

    module.Client = _FakeClientFactory
    module.EventDispatcherHandler = _FakeEventDispatcherHandler
    module.ws = _FakeWsNamespace()
    module.LogLevel = _FakeLogLevel
    return module


class _PatchedThread(threading.Thread):
    def start(self) -> None:
        target = getattr(self, "_target", None)
        if getattr(target, "__name__", "") in {"run_ws", "_health_check_loop"}:
            return None
        return super().start()


@pytest.mark.asyncio
async def test_mark_message_processed_uses_shared_redis_dedup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr("src.infra.channel.feishu.channel.get_redis_client", lambda: fake_redis)

    first = _build_channel()
    second = _build_channel()

    assert await first._mark_message_processed("msg-1") is True
    assert await second._mark_message_processed("msg-1") is False


@pytest.mark.asyncio
async def test_mark_message_processed_skips_redis_after_local_cache_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr("src.infra.channel.feishu.channel.get_redis_client", lambda: fake_redis)

    channel = _build_channel()

    assert await channel._mark_message_processed("msg-1") is True
    redis_keys_after_first = dict(fake_redis.values)

    assert await channel._mark_message_processed("msg-1") is False
    assert fake_redis.values == redis_keys_after_first


@pytest.mark.asyncio
async def test_message_metadata_includes_received_reaction_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _build_channel()
    captured: dict[str, object] = {}

    async def _mark_processed(_message_id: str) -> bool:
        return True

    async def _add_reaction(_message_id: str, _emoji: str) -> str:
        return "reaction-1"

    async def _handle_message(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(channel, "_mark_message_processed", _mark_processed)
    monkeypatch.setattr(channel, "_add_reaction", _add_reaction)
    monkeypatch.setattr(channel, "_handle_message", _handle_message)

    await channel._on_message(
        _build_message_event(
            message_type="text",
            content='{"text":"hello"}',
        )
    )

    assert captured["metadata"]["reaction_id"] == "reaction-1"


@pytest.mark.asyncio
async def test_on_message_offloads_content_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _build_channel()
    captured: dict[str, object] = {}
    calls: list[tuple[Any, tuple[Any, ...]]] = []

    async def _mark_processed(_message_id: str) -> bool:
        return True

    async def _add_reaction(_message_id: str, _emoji: str) -> str:
        return "reaction-1"

    async def _handle_message(**kwargs):
        captured.update(kwargs)

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        calls.append((func, args))
        return func(*args, **kwargs)

    monkeypatch.setattr(channel, "_mark_message_processed", _mark_processed)
    monkeypatch.setattr(channel, "_add_reaction", _add_reaction)
    monkeypatch.setattr(channel, "_handle_message", _handle_message)
    monkeypatch.setattr("src.infra.channel.feishu.channel.run_blocking_io", _fake_run_blocking_io)

    await channel._on_message(
        _build_message_event(
            message_type="text",
            content='{"text":"hello"}',
        )
    )

    assert captured["content"] == "hello"
    assert calls == [(json.loads, ('{"text":"hello"}',))]


@pytest.mark.asyncio
async def test_on_message_offloads_share_card_content_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.channel.feishu import channel as feishu_channel

    channel = _build_channel()
    captured: dict[str, object] = {}
    calls: list[tuple[Any, tuple[Any, ...]]] = []

    async def _mark_processed(_message_id: str) -> bool:
        return True

    async def _add_reaction(_message_id: str, _emoji: str) -> str:
        return "reaction-1"

    async def _handle_message(**kwargs):
        captured.update(kwargs)

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        calls.append((func, args))
        return func(*args, **kwargs)

    monkeypatch.setattr(channel, "_mark_message_processed", _mark_processed)
    monkeypatch.setattr(channel, "_add_reaction", _add_reaction)
    monkeypatch.setattr(channel, "_handle_message", _handle_message)
    monkeypatch.setattr(feishu_channel, "run_blocking_io", _fake_run_blocking_io)

    await channel._on_message(
        _build_message_event(
            message_type="interactive",
            content='{"title":"hello card"}',
        )
    )

    assert captured["content"] == "title: hello card"
    assert calls == [
        (json.loads, ('{"title":"hello card"}',)),
        (feishu_channel.extract_share_card_content, ({"title": "hello card"}, "interactive")),
    ]


@pytest.mark.asyncio
async def test_start_imports_lark_sdk_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_lark = _build_fake_lark_module()
    import_threads: list[int] = []
    main_thread_id = threading.get_ident()

    def _import_module(name: str):
        if name == "lark_oapi":
            import_threads.append(threading.get_ident())
            return fake_lark
        raise AssertionError(f"unexpected import: {name}")

    monkeypatch.setattr("src.infra.channel.feishu.channel.FEISHU_AVAILABLE", True)
    monkeypatch.setattr("src.infra.channel.feishu.channel.threading.Thread", _PatchedThread)
    monkeypatch.setattr("src.infra.channel.feishu.channel.importlib.import_module", _import_module)

    channel = _build_channel()

    assert await channel.start() is True
    assert import_threads
    assert import_threads[0] != main_thread_id


@pytest.mark.asyncio
async def test_ws_client_disables_sdk_info_connection_url_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class _FakeWsClient:
        def __init__(self, _app_id: str, _app_secret: str, **kwargs: object) -> None:
            captured.update(kwargs)
            self._reconnect_interval = None
            self._reconnect_nonce = None

        async def _disconnect(self) -> None:
            return None

    monkeypatch.setattr("lark_oapi.ws.Client", _FakeWsClient)
    channel = _build_channel()
    channel._running = False

    await channel._run_ws_client(event_handler=object())

    log_level = captured["log_level"]
    assert getattr(log_level, "name", None) == "WARNING"


@pytest.mark.asyncio
async def test_ws_connection_error_log_omits_exception_details(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_url = "wss://open.feishu.cn/ws?token=private-token"

    class _FakeWsClient:
        def __init__(self, _app_id: str, _app_secret: str, **_kwargs: object) -> None:
            self._reconnect_interval = None
            self._reconnect_nonce = None

        async def _connect(self) -> None:
            raise ConnectionError(secret_url)

        async def _disconnect(self) -> None:
            return None

    channel = _build_channel()

    async def _stop_after_retry(_delay: float) -> None:
        channel._running = False

    monkeypatch.setattr("lark_oapi.ws.Client", _FakeWsClient)
    monkeypatch.setattr("src.infra.channel.feishu.channel.asyncio.sleep", _stop_after_retry)
    channel._running = True

    with caplog.at_level(logging.WARNING):
        await channel._run_ws_client(event_handler=object())

    assert secret_url not in caplog.text
    assert "ConnectionError" in caplog.text


@pytest.mark.asyncio
async def test_stop_waits_for_websocket_futures_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = _build_channel()
    ws_cleanup_finished = False
    health_cleanup_finished = False
    ws_started = asyncio.Event()
    health_started = asyncio.Event()

    async def _ws_forever() -> None:
        nonlocal ws_cleanup_finished
        ws_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            ws_cleanup_finished = True

    async def _health_forever() -> None:
        nonlocal health_cleanup_finished
        health_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            health_cleanup_finished = True

    async def _close_http_client() -> None:
        return None

    monkeypatch.setattr(channel, "close_feishu_http_client", _close_http_client)

    channel._ws_future = asyncio.create_task(_ws_forever())
    channel._health_check_future = asyncio.create_task(_health_forever())
    await ws_started.wait()
    await health_started.wait()

    await channel.stop()

    assert channel._ws_future.cancelled() is True
    assert channel._health_check_future.cancelled() is True
    assert ws_cleanup_finished is True
    assert health_cleanup_finished is True


@pytest.mark.asyncio
async def test_audio_message_uses_configured_transcription_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    channel = FeishuChannel(
        FeishuConfig(
            user_id="user-1",
            instance_id="instance-1",
            app_id="app-id",
            app_secret="app-secret",
            encrypt_key="",
            verification_token="",
            react_emoji="THUMBSUP",
            group_policy=FeishuGroupPolicy.MENTION,
            enabled=True,
            audio_transcribe_prompt="Please transcribe this voice message.",
        )
    )
    captured: dict[str, object] = {}

    async def _mark_processed(_message_id: str) -> bool:
        return True

    async def _add_reaction(_message_id: str, _emoji: str) -> str:
        return "reaction-1"

    async def _download_resource(*_args, **_kwargs):
        return {
            "key": "audio-key",
            "name": "voice.opus",
            "type": "audio",
            "url": "https://example.test/voice.opus",
        }

    async def _handle_message(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(channel, "_mark_message_processed", _mark_processed)
    monkeypatch.setattr(channel, "_add_reaction", _add_reaction)
    monkeypatch.setattr(channel, "_download_and_store_resource", _download_resource)
    monkeypatch.setattr(channel, "_handle_message", _handle_message)

    await channel._on_message(
        _build_message_event(
            message_type="audio",
            content='{"file_key":"file-1","file_name":"voice"}',
        )
    )

    assert captured["content"] == "Please transcribe this voice message."
    assert captured["metadata"]["attachments"][0]["type"] == "audio"


def test_card_action_response_payload_removes_approval_buttons() -> None:
    channel = _build_channel()
    payload = channel._build_card_action_response_payload(
        _build_card_action_event(
            {
                "action": "lambchat.approval",
                "approval_id": "approval-1",
                "approved": True,
            }
        )
    )

    assert payload["toast"]["type"] == "success"
    assert payload["card"]["type"] == "raw"
    card = payload["card"]["data"]
    assert "正在处理" in card["elements"][2]["content"]
    assert all(element.get("tag") != "action" for element in card["elements"])
