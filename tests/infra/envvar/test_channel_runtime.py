from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import src.agents  # noqa: F401
from src.infra.envvar import sync


async def test_channel_environment_is_resolved_using_authenticated_owner(monkeypatch):
    from src.infra.channel.channel_storage import ChannelStorage
    from src.kernel.schemas.channel import ChannelType

    values = {"API_KEY": "channel-secret"}
    get_config = AsyncMock(
        return_value={"user_id": "owner", "runtime_config": {"env_vars": values}}
    )
    monkeypatch.setattr(ChannelStorage, "get_config", get_config)
    options = {
        "channel_runtime": {
            "channel_type": "telegram",
            "instance_id": "bot-1",
            "user_id": "attacker",
        }
    }

    result = await sync.resolve_channel_env_vars("owner", options)

    get_config.assert_awaited_once_with("owner", ChannelType.TELEGRAM, "bot-1")
    assert result == values
    assert result is not values
    assert "channel-secret" not in str(options)


@pytest.mark.parametrize(
    "stored", [None, {"user_id": "foreign", "runtime_config": {"env_vars": {"SECRET": "hidden"}}}]
)
async def test_missing_or_foreign_channel_environment_fails_closed(monkeypatch, stored):
    from src.infra.channel.channel_storage import ChannelStorage

    monkeypatch.setattr(ChannelStorage, "get_config", AsyncMock(return_value=stored))
    with pytest.raises(ValueError, match="Channel runtime configuration unavailable"):
        await sync.resolve_channel_env_vars(
            "owner", {"channel_runtime": {"channel_type": "telegram", "instance_id": "bot-1"}}
        )


async def test_channel_overrides_are_run_scoped_and_survive_global_environment_refresh(monkeypatch):
    global_values = {"SHARED": "global", "TOKEN": "global-token"}
    first = SimpleNamespace(env_vars=global_values)
    second = SimpleNamespace(env_vars=global_values)
    overrides = {"TOKEN": "first-secret"}
    sync.apply_sandbox_env_overrides(first, overrides)
    sync.apply_sandbox_env_overrides(second, {"TOKEN": "second-secret"})
    overrides["TOKEN"] = "changed-input"
    monkeypatch.setattr(
        sync,
        "EnvVarStorage",
        lambda: SimpleNamespace(
            get_decrypted_vars=AsyncMock(return_value={"NEW": "new", "TOKEN": "updated-global"})
        ),
    )

    await sync.sync_sandbox_env_vars(first, "owner")

    assert first.env_vars == {"NEW": "new", "TOKEN": "first-secret"}
    assert second.env_vars == {"SHARED": "global", "TOKEN": "second-secret"}
    assert global_values == {"SHARED": "global", "TOKEN": "global-token"}


async def test_regular_chat_never_reads_channel_environment(monkeypatch):
    from src.infra.channel.channel_storage import ChannelStorage

    get_config = AsyncMock()
    monkeypatch.setattr(ChannelStorage, "get_config", get_config)
    assert await sync.resolve_channel_env_vars("owner", {}) == {}
    get_config.assert_not_awaited()


@pytest.mark.parametrize(
    "reference",
    [None, {}, {"channel_type": "telegram"}, {"channel_type": "invalid", "instance_id": "bot-1"}],
)
async def test_invalid_channel_reference_never_falls_back_to_any_instance(monkeypatch, reference):
    from src.infra.channel.channel_storage import ChannelStorage

    get_config = AsyncMock()
    monkeypatch.setattr(ChannelStorage, "get_config", get_config)
    with pytest.raises(ValueError, match="Channel runtime configuration unavailable"):
        await sync.resolve_channel_env_vars("owner", {"channel_runtime": reference})
    get_config.assert_not_awaited()


async def test_environment_lookup_failure_does_not_expose_storage_error(monkeypatch):
    from src.infra.channel.channel_storage import ChannelStorage

    monkeypatch.setattr(
        ChannelStorage, "get_config", AsyncMock(side_effect=RuntimeError("secret-value"))
    )
    with pytest.raises(ValueError) as captured:
        await sync.resolve_channel_env_vars(
            "owner", {"channel_runtime": {"channel_type": "telegram", "instance_id": "bot-1"}}
        )
    assert str(captured.value) == "Channel runtime configuration unavailable"
    assert captured.value.__suppress_context__


async def test_lazy_delegate_refresh_keeps_channel_override(monkeypatch):
    delegate = SimpleNamespace(env_vars={"OLD": "old"})
    sync.apply_sandbox_env_overrides(delegate, {"TOKEN": "channel-secret"})
    lazy = SimpleNamespace(_delegate=delegate)
    backend = SimpleNamespace(default=lazy)
    monkeypatch.setattr(
        sync,
        "EnvVarStorage",
        lambda: SimpleNamespace(
            get_decrypted_vars=AsyncMock(return_value={"NEW": "new", "TOKEN": "global"})
        ),
    )
    await sync.sync_sandbox_env_vars(backend, "owner")
    assert delegate.env_vars == {"NEW": "new", "TOKEN": "channel-secret"}
