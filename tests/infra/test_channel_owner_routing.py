"""Connection-bound outgoing messages must reach the instance's owning node."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from src.infra.channel.manager import ChannelCoordinator
from src.kernel.schemas.channel import ChannelType


async def test_non_owner_wecom_routes_to_durable_owner_queue(monkeypatch):
    channel = SimpleNamespace(
        _connected=False, config=SimpleNamespace(receive_enabled=True), send_message=AsyncMock()
    )
    manager = SimpleNamespace(get_channel=Mock(return_value=channel))
    coordinator = ChannelCoordinator()
    monkeypatch.setattr(coordinator, "_resolve_manager", lambda kind: manager)
    route = AsyncMock(return_value=True)
    monkeypatch.setattr("src.infra.channel.manager.send_via_owner", route, raising=False)
    assert await coordinator.send_message("u", ChannelType.WECOM, "chat", "hello", "i")
    route.assert_awaited_once_with("u", ChannelType.WECOM, "chat", "hello", "i")
    channel.send_message.assert_not_awaited()


async def test_absent_local_feishu_uses_exact_remote_instance(monkeypatch):
    coordinator = ChannelCoordinator()
    monkeypatch.setattr(
        coordinator,
        "_resolve_manager",
        lambda kind: SimpleNamespace(get_channel=Mock(return_value=None)),
    )
    route = AsyncMock(return_value=True)
    monkeypatch.setattr("src.infra.channel.manager.send_via_owner", route, raising=False)
    assert await coordinator.send_message("u", ChannelType.FEISHU, "chat", "hello", "requested")
    route.assert_awaited_once_with("u", ChannelType.FEISHU, "chat", "hello", "requested")
