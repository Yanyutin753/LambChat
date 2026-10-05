from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.channel.feishu.manager import FeishuChannelManager
from src.infra.channel.ntfy import NtfyChannelManager
from src.infra.channel.weixin.manager import WeixinChannelManager


@pytest.mark.parametrize(
    "manager_cls", [NtfyChannelManager, WeixinChannelManager, FeishuChannelManager]
)
def test_explicit_missing_instance_never_selects_another_bot(manager_cls):
    manager = manager_cls()
    other = SimpleNamespace()
    manager._channels = {"user:other": other, "user": other}
    assert manager.get_channel("user", "missing") is None
    if isinstance(manager, FeishuChannelManager):
        assert manager._find_channel("user", "missing") is None
    assert manager.get_channel("user") is other


class Storage:
    def __init__(self):
        self.config = {"user_id": "user", "instance_id": "bot", "enabled": True, "version": 1}

    async def list_user_configs_by_type(self, *_):
        return [dict(self.config)] if self.config else []

    async def iter_enabled_configs(self, *_):
        if self.config:
            yield dict(self.config)


@pytest.mark.parametrize("manager_cls", [NtfyChannelManager, WeixinChannelManager])
async def test_concurrent_reload_stops_previous_reader_and_keeps_latest_config(manager_cls):
    manager = manager_cls()
    manager._storage = storage = Storage()
    entered, release = asyncio.Event(), asyncio.Event()
    channels = []

    def build(config):
        channel = SimpleNamespace(config=config, is_running=True, stop=AsyncMock())

        async def start():
            if config["version"] == 1:
                entered.set()
                await release.wait()
            return True

        channel.start = start
        channels.append(channel)
        return channel

    manager._build_channel = build
    first = asyncio.create_task(manager.reload_user("user", "bot"))
    await entered.wait()
    storage.config["version"] = 2
    second = asyncio.create_task(manager.reload_user("user", "bot"))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    try:
        assert manager.get_channel("user", "bot").config["version"] == 2
        channels[0].stop.assert_awaited_once()
    finally:
        await manager.stop()


async def test_feishu_rebalance_retries_transient_failure(monkeypatch):
    manager = FeishuChannelManager()
    manager._running = True
    recovered = asyncio.Event()
    calls = 0

    async def reconcile():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("temporary database outage")
        recovered.set()
        manager._running = False
        return 0, 0

    manager._reconcile_enabled_configs = reconcile
    monkeypatch.setattr("src.infra.channel.feishu.manager._FEISHU_REBALANCE_INTERVAL", 0)
    await manager._rebalance_loop()
    assert recovered.is_set()


@pytest.mark.parametrize("manager_cls", [NtfyChannelManager, WeixinChannelManager])
async def test_reconciliation_recovers_failed_start_and_lost_config_notification(manager_cls):
    manager = manager_cls()
    manager._storage = storage = Storage()
    manager._reconcile_interval = 0.001
    channels = []
    failed = True

    def build(config):
        nonlocal failed
        channel = SimpleNamespace(config=config, is_running=True, stop=AsyncMock())
        channel.start = AsyncMock(return_value=not failed)
        failed = False
        channels.append(channel)
        return channel

    manager._build_channel = build
    await manager.start()
    try:
        async with asyncio.timeout(0.2):
            while manager.get_channel("user", "bot") is None:
                await asyncio.sleep(0.001)
        storage.config["version"] = 2
        async with asyncio.timeout(0.2):
            while manager.get_channel("user", "bot").config["version"] != 2:
                await asyncio.sleep(0.001)
        storage.config = None
        async with asyncio.timeout(0.2):
            while manager.get_channel("user", "bot") is not None:
                await asyncio.sleep(0.001)
    finally:
        await manager.stop()
    assert all(channel.stop.await_count == 1 for channel in channels)


async def test_feishu_reconcile_refreshes_changed_secret_without_notification(monkeypatch):
    manager = FeishuChannelManager()
    storage = Storage()
    storage.config.update(app_id="app", app_secret="old")
    manager._storage = storage
    manager._refresh_node_membership = AsyncMock(return_value=True)
    manager._list_active_node_ids = AsyncMock(return_value=[manager._instance_id])
    manager._acquire_lease = AsyncMock(return_value=True)
    manager._release_lease = AsyncMock()
    manager._ensure_lease_refresh_task = lambda _: None
    channels = []

    def build(config, handler):
        channel = SimpleNamespace(
            config=config,
            message_handler=handler,
            is_running=True,
            stop=AsyncMock(),
            start=AsyncMock(return_value=True),
        )
        channels.append(channel)
        return channel

    monkeypatch.setattr("src.infra.channel.feishu.manager.FeishuChannel", build)
    await manager._reconcile_enabled_configs()
    storage.config["app_secret"] = "new"
    await manager._reconcile_enabled_configs()
    assert manager.get_channel("user", "bot").config.app_secret == "new"
    channels[0].stop.assert_awaited_once()
    manager._release_lease.assert_awaited_once_with("app")


@pytest.mark.parametrize(
    "manager_cls", [NtfyChannelManager, WeixinChannelManager, FeishuChannelManager]
)
async def test_shutdown_prevents_queued_reload_restarting_channels(manager_cls):
    manager = manager_cls()
    manager._storage = SimpleNamespace(close=AsyncMock())
    if isinstance(manager, FeishuChannelManager):
        manager._unregister_node = AsyncMock()
    await manager.stop()
    assert await manager.reload_user("user", "bot") is False
    assert manager._channels == {}


async def test_feishu_concurrent_reload_preserves_latest_configuration(monkeypatch):
    manager = FeishuChannelManager()
    config = {"app_id": "app", "app_secret": "old"}
    entered, release = asyncio.Event(), asyncio.Event()
    channels = []

    async def get_config(*_):
        return dict(config)

    manager._storage = SimpleNamespace(get_config=get_config)
    manager._refresh_node_membership = AsyncMock(return_value=True)
    manager._list_active_node_ids = AsyncMock(return_value=[manager._instance_id])
    manager._acquire_lease = AsyncMock(return_value=True)
    manager._release_lease = AsyncMock()
    manager._ensure_lease_refresh_task = lambda _: None

    def build(cfg, handler):
        async def start():
            if cfg.app_secret == "old":
                entered.set()
                await release.wait()
            return True

        channel = SimpleNamespace(config=cfg, start=start, stop=AsyncMock())
        channels.append(channel)
        return channel

    monkeypatch.setattr("src.infra.channel.feishu.manager.FeishuChannel", build)
    first = asyncio.create_task(manager.reload_user("user", "bot"))
    await entered.wait()
    config["app_secret"] = "new"
    second = asyncio.create_task(manager.reload_user("user", "bot"))
    await asyncio.sleep(0)
    release.set()
    await asyncio.gather(first, second)
    assert manager.get_channel("user", "bot").config.app_secret == "new"
    channels[0].stop.assert_awaited_once()


@pytest.mark.parametrize("manager_cls", [NtfyChannelManager, WeixinChannelManager])
async def test_cancelled_start_closes_partial_channel(manager_cls):
    manager = manager_cls()
    manager._storage = Storage()
    entered = asyncio.Event()

    async def start():
        entered.set()
        await asyncio.Event().wait()

    channel = SimpleNamespace(start=start, stop=AsyncMock())
    manager._build_channel = lambda _: channel
    task = asyncio.create_task(manager.reload_user("user", "bot"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    channel.stop.assert_awaited_once()
    assert manager._channels == {}


async def test_feishu_reload_waits_for_lost_lease_reader_cleanup(monkeypatch):
    manager = FeishuChannelManager()
    entered, release = asyncio.Event(), asyncio.Event()

    async def stop():
        entered.set()
        await release.wait()

    manager._channels["user:bot"] = SimpleNamespace(stop=stop)
    manager._active_app_ids["app"] = "user:bot"
    manager._storage = SimpleNamespace(
        get_config=AsyncMock(return_value={"app_id": "app", "app_secret": "secret"})
    )
    manager._refresh_node_membership = AsyncMock(return_value=False)
    manager._start_user_client = AsyncMock(return_value=True)
    lost = asyncio.create_task(manager._stop_channel_after_lost_lease("app"))
    await entered.wait()
    reload = asyncio.create_task(manager.reload_user("user", "bot"))
    await asyncio.sleep(0)
    try:
        manager._start_user_client.assert_not_awaited()
    finally:
        release.set()
        await asyncio.gather(lost, reload)
    manager._start_user_client.assert_awaited_once()


@pytest.mark.parametrize("outcome", ["false", "exception", "cancel"])
async def test_feishu_partial_start_stops_worker_before_releasing_lease(monkeypatch, outcome):
    manager = FeishuChannelManager()
    manager._acquire_lease = AsyncMock(return_value=True)
    order = []
    started = asyncio.Event()
    worker = None

    async def start():
        nonlocal worker
        worker = asyncio.create_task(asyncio.Event().wait())
        started.set()
        if outcome == "false":
            return False
        if outcome == "exception":
            raise RuntimeError("SDK initialization failed")
        await asyncio.Event().wait()

    async def stop():
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        order.append("stopped")

    async def release(app_id):
        order.append("released")
        assert app_id == "app"
        assert worker.done()

    client = SimpleNamespace(start=start, stop=AsyncMock(side_effect=stop))
    manager._release_lease = AsyncMock(side_effect=release)
    monkeypatch.setattr("src.infra.channel.feishu.manager.FeishuChannel", lambda *_: client)
    config = manager._dict_to_config("user", {"app_id": "app", "app_secret": "secret"}, "bot")
    task = asyncio.create_task(manager._start_user_client(config))
    await started.wait()
    if outcome == "cancel":
        task.cancel()
    try:
        if outcome == "false":
            assert await task is False
        elif outcome == "exception":
            with pytest.raises(RuntimeError, match="SDK initialization failed"):
                await task
        else:
            with pytest.raises(asyncio.CancelledError):
                await task
        client.stop.assert_awaited_once()
        manager._release_lease.assert_awaited_once_with("app")
        assert order == ["stopped", "released"]
        assert manager._channels == {}
        assert manager._active_app_ids == {}
    finally:
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)


async def test_feishu_constructor_failure_releases_acquired_lease(monkeypatch):
    manager = FeishuChannelManager()
    manager._acquire_lease = AsyncMock(return_value=True)
    manager._release_lease = AsyncMock()

    def construct(*_):
        raise RuntimeError("construction failed")

    monkeypatch.setattr("src.infra.channel.feishu.manager.FeishuChannel", construct)
    config = manager._dict_to_config("user", {"app_id": "app", "app_secret": "secret"}, "bot")
    with pytest.raises(RuntimeError, match="construction failed"):
        await manager._start_user_client(config)
    manager._release_lease.assert_awaited_once_with("app")
