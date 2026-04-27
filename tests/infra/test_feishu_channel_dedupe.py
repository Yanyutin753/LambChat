from __future__ import annotations

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
