from __future__ import annotations

import pytest

from src.infra.channel.feishu.manager import FeishuChannelManager
from src.kernel.schemas.feishu import FeishuConfig, FeishuGroupPolicy


class _FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.deleted: list[str] = []
        self.closed = False

    async def set(
        self,
        key: str,
        value: str,
        nx: bool = False,
        ex: int | None = None,
        xx: bool = False,
    ):
        if nx and key in self.values:
            return False
        if xx and key not in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        self.expirations.pop(key, None)
        self.deleted.append(key)
        return 1 if existed else 0

    async def eval(self, script: str, numkeys: int, key: str, value: str) -> int:
        if self.values.get(key) == value:
            await self.delete(key)
            return 1
        return 0

    async def aclose(self) -> None:
        self.closed = True


class _FakeChannel:
    def __init__(self, config, message_handler) -> None:
        self.config = config
        self.message_handler = message_handler
        self.stopped = False
        self._running = False

    async def start(self) -> bool:
        self._running = True
        return True

    async def stop(self) -> None:
        self.stopped = True
        self._running = False


def _config(instance_id: str = "inst-1", app_id: str = "app-1") -> FeishuConfig:
    return FeishuConfig(
        user_id="user-1",
        instance_id=instance_id,
        app_id=app_id,
        app_secret="secret",
        encrypt_key="",
        verification_token="",
        react_emoji="THUMBSUP",
        group_policy=FeishuGroupPolicy.MENTION,
        enabled=True,
    )


@pytest.mark.asyncio
async def test_start_user_client_skips_when_lease_is_held_by_other_instance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    fake_redis.values["feishu:lease:app-1"] = "other-instance"
    isolated_pool_flags: list[bool] = []
    monkeypatch.setattr(
        "src.infra.channel.feishu.manager.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or fake_redis,
    )
    monkeypatch.setattr("src.infra.channel.feishu.manager.FeishuChannel", _FakeChannel)

    manager = FeishuChannelManager()
    manager._instance_id = "instance-a"

    started = await manager._start_user_client(_config())

    assert started is False
    assert manager._channels == {}
    assert isolated_pool_flags == [True]


@pytest.mark.asyncio
async def test_start_user_client_registers_channel_when_lease_acquired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    isolated_pool_flags: list[bool] = []
    monkeypatch.setattr(
        "src.infra.channel.feishu.manager.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or fake_redis,
    )
    monkeypatch.setattr("src.infra.channel.feishu.manager.FeishuChannel", _FakeChannel)

    manager = FeishuChannelManager()
    manager._instance_id = "instance-a"

    started = await manager._start_user_client(_config(instance_id="inst-9", app_id="app-9"))

    assert started is True
    assert "user-1:inst-9" in manager._channels
    assert fake_redis.values["feishu:lease:app-9"] == "instance-a"
    assert isolated_pool_flags == [True]

    await manager.stop()
    assert fake_redis.closed is True


@pytest.mark.asyncio
async def test_stop_releases_owned_leases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    isolated_pool_flags: list[bool] = []
    monkeypatch.setattr(
        "src.infra.channel.feishu.manager.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or fake_redis,
    )
    monkeypatch.setattr("src.infra.channel.feishu.manager.FeishuChannel", _FakeChannel)

    manager = FeishuChannelManager()
    manager._instance_id = "instance-a"
    await manager._start_user_client(_config(instance_id="inst-2", app_id="app-2"))

    assert fake_redis.values["feishu:lease:app-2"] == "instance-a"

    await manager.stop()

    assert "feishu:lease:app-2" in fake_redis.deleted
    assert fake_redis.closed is True
    assert isolated_pool_flags == [True]
