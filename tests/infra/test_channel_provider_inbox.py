"""Provider acknowledgement must follow durable acceptance, never execution."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.channel.feishu.channel import FeishuChannel
from src.infra.channel.weixin.channel import WeixinChannel
from src.kernel.schemas.feishu import FeishuConfig
from src.kernel.schemas.weixin import WeixinConfig


def weixin():
    return WeixinChannel(WeixinConfig(user_id="u", instance_id="i", bot_token="token"), AsyncMock())


def feishu():
    return FeishuChannel(
        FeishuConfig(user_id="u", instance_id="i", app_id="app", app_secret="secret"), AsyncMock()
    )


def event():
    return SimpleNamespace(
        event=SimpleNamespace(
            message=SimpleNamespace(
                message_id="m",
                content='{"text":"hello"}',
                chat_id="c",
                chat_type="p2p",
                message_type="text",
            ),
            sender=SimpleNamespace(sender_type="user", sender_id=SimpleNamespace(open_id="s")),
        )
    )


async def test_weixin_persists_before_advancing_cursor_without_executing(monkeypatch):
    channel = weixin()
    accepted = asyncio.Event()
    release = asyncio.Event()

    async def accept(message):
        accepted.set()
        await release.wait()
        assert message["metadata"]["context_token"] == "ctx"
        return True

    channel._inbox_worker = SimpleNamespace(accept=accept)
    monkeypatch.setattr(channel, "_get_http", AsyncMock())
    monkeypatch.setattr(
        "src.infra.channel.weixin.provider.get_updates",
        AsyncMock(
            return_value=(
                [
                    {
                        "message_id": "m",
                        "sender_id": "s",
                        "chat_id": "s",
                        "content": "hello",
                        "context_token": "ctx",
                    }
                ],
                "after",
            )
        ),
    )
    storage = AsyncMock()
    storage.get.return_value = "before"
    task = asyncio.create_task(channel._consume_once(storage))
    try:
        await asyncio.wait_for(accepted.wait(), 0.2)
        storage.set.assert_not_awaited()
        channel.message_handler.assert_not_awaited()
        release.set()
        await task
        storage.set.assert_awaited_once_with(
            "weixin:buf:" + ":".join(channel._reader_scope), "after"
        )
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_weixin_enqueue_failure_preserves_cursor(monkeypatch):
    channel = weixin()
    channel._inbox_worker = SimpleNamespace(accept=AsyncMock(side_effect=OSError("database down")))
    monkeypatch.setattr(channel, "_get_http", AsyncMock())
    monkeypatch.setattr(
        "src.infra.channel.weixin.provider.get_updates",
        AsyncMock(
            return_value=(
                [{"message_id": "m", "sender_id": "s", "chat_id": "s", "content": "hello"}],
                "after",
            )
        ),
    )
    storage = AsyncMock()
    storage.get.return_value = "before"
    with pytest.raises(OSError):
        await channel._consume_once(storage)
    storage.set.assert_not_awaited()


async def test_weixin_start_does_not_drop_on_transient_verify_failure(monkeypatch):
    channel = weixin()
    monkeypatch.setattr(
        "src.infra.channel.weixin.provider.verify_token", AsyncMock(return_value=False)
    )
    monkeypatch.setattr(channel, "_poll_loop", AsyncMock())
    assert await channel.start()
    await channel.stop()


async def test_feishu_callback_waits_for_durable_accept_and_propagates_failure(monkeypatch):
    channel = feishu()
    channel._loop = asyncio.get_running_loop()
    channel._running = True
    accepted = asyncio.Event()
    release = asyncio.Event()

    async def accept(message):
        accepted.set()
        await release.wait()
        raise OSError("database down")

    channel._inbox_worker = SimpleNamespace(accept=accept)
    monkeypatch.setattr(channel, "_add_reaction", AsyncMock(return_value=None))
    task = asyncio.create_task(asyncio.to_thread(channel._on_message_sync, event()))
    try:
        await asyncio.wait_for(accepted.wait(), 0.2)
        assert not task.done()
        channel.message_handler.assert_not_awaited()
        release.set()
        with pytest.raises(OSError):
            await task
    finally:
        release.set()
        await asyncio.gather(task, return_exceptions=True)


async def test_feishu_stop_joins_active_callback_before_stopping_inbox(monkeypatch):
    channel = feishu()
    channel._loop = asyncio.get_running_loop()
    channel._running = True
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def receive(data):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0.01)
            cleaned.set()

    async def stop():
        assert cleaned.is_set()

    monkeypatch.setattr(channel, "_on_message", receive)
    monkeypatch.setattr(channel._inbox_worker, "stop", stop)
    task = asyncio.create_task(asyncio.to_thread(channel._on_message_sync, event()))
    await started.wait()
    try:
        await channel.stop()
        assert cleaned.is_set()
    finally:
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("factory", [feishu, weixin])
async def test_outbound_inbox_failure_retries_without_agent(factory, monkeypatch):
    channel = factory()
    send = AsyncMock(return_value=False)
    monkeypatch.setattr(channel, "send_message", send)
    with pytest.raises(RuntimeError, match="outbound"):
        await channel._deliver_inbox_message(
            {"outbound": True, "chat_id": "c", "content": "result"}
        )
    send.assert_awaited_once_with("c", "result")
    channel.message_handler.assert_not_awaited()


async def test_weixin_lease_loss_stops_worker_before_releasing_reader(monkeypatch):
    from src.infra.channel.weixin import channel as module

    channel = weixin()
    channel._running = True
    worker_started = asyncio.Event()
    worker_stopped = asyncio.Event()

    async def run():
        worker_started.set()
        await asyncio.Event().wait()

    async def stop():
        worker_stopped.set()

    async def renew(*args):
        await worker_started.wait()
        return False

    async def release(*args):
        assert worker_stopped.is_set()
        channel._running = False

    monkeypatch.setattr(channel._inbox_worker, "run", run)
    monkeypatch.setattr(channel._inbox_worker, "stop", stop)
    monkeypatch.setattr(module, "_acquire_poll_lock", AsyncMock(return_value=True))
    monkeypatch.setattr(module, "_renew_poll_lock", renew)
    monkeypatch.setattr(module, "_release_poll_lock", release)
    await asyncio.wait_for(channel._poll_loop(), 0.2)
    assert worker_stopped.is_set()
    assert channel._inbox_task is None


async def test_weixin_context_survives_channel_recreation_and_is_scoped(monkeypatch):
    from src.infra.storage.redis import RedisStorage

    stored = {}

    async def save(self, key, value, **kwargs):
        stored[key] = value

    async def get(self, key):
        return stored.get(key)

    monkeypatch.setattr(RedisStorage, "set", save)
    monkeypatch.setattr(RedisStorage, "get", get)
    monkeypatch.setattr(
        "src.infra.mcp.encryption.encrypt_value", lambda data: "encrypted:" + data["value"]
    )
    monkeypatch.setattr(
        "src.infra.mcp.encryption.decrypt_value",
        lambda value: {"value": value.removeprefix("encrypted:")},
    )
    first = weixin()
    await first._deliver_inbox_message(
        {
            "message_id": "m",
            "sender_id": "s",
            "chat_id": "s",
            "content": "hi",
            "metadata": {"context_token": "ctx"},
        }
    )
    replacement = weixin()
    assert await replacement._cached_context_token("s") == "ctx"
    other = WeixinChannel(WeixinConfig(user_id="other", instance_id="i", bot_token="token"))
    assert await other._cached_context_token("s") is None
    assert list(stored.values()) == ["encrypted:ctx"]


async def test_weixin_shared_cursor_imports_legacy_once_while_both_leases_owned(monkeypatch):
    from src.infra.channel.weixin import channel as module

    channel = weixin()
    channel._lock_owner = "owner"
    values = {"weixin:buf:u:i": "legacy"}
    storage = AsyncMock()
    storage.get.side_effect = lambda key: values.get(key)

    async def save(key, value):
        values[key] = value

    storage.set.side_effect = save
    renew = AsyncMock(return_value=True)
    updates = AsyncMock(return_value=([], "advanced"))
    monkeypatch.setattr(module, "_renew_poll_lock", renew)
    monkeypatch.setattr(channel, "_get_http", AsyncMock())
    monkeypatch.setattr(module.provider, "get_updates", updates)
    await channel._consume_once(storage)
    assert updates.await_args.args[2] == "legacy"
    shared_key = module._buf_key(*channel._reader_scope)
    assert values[shared_key] == "advanced"
    assert values["weixin:buf:u:i"] == "advanced"
    assert {call.args[:2] for call in renew.await_args_list} == {channel._reader_scope, ("u", "i")}

    # A second instance with the same credential must use shared progress rather
    # than re-import its own stale cursor.
    replacement = WeixinChannel(WeixinConfig(user_id="other", instance_id="j", bot_token="token"))
    replacement._lock_owner = "next-owner"
    values["weixin:buf:other:j"] = "stale"
    monkeypatch.setattr(replacement, "_get_http", AsyncMock())
    await replacement._consume_once(storage)
    assert updates.await_args.args[2] == "advanced"
