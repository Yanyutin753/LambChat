from unittest.mock import AsyncMock

import pytest

from src.api.routes import channels
from src.api.routes.channel_runtime_configuration import validate_runtime_configuration
from src.infra.channel.channel_storage import ChannelStorage
from src.kernel.errors import AppError
from src.kernel.schemas.channel import ChannelType
from src.kernel.schemas.user import TokenPayload


async def test_runtime_machine_must_belong_to_channel_owner(monkeypatch):
    machines = AsyncMock(return_value=[{"machine_id": "mine", "online": False}])
    monkeypatch.setattr(
        "src.infra.sandbox.relay.registry.SandboxClientRegistry.list_machines", machines
    )
    with pytest.raises(AppError):
        await validate_runtime_configuration(
            {"sandbox": "local", "sandbox_machine_id": "other"}, "owner"
        )
    result = await validate_runtime_configuration(
        {"sandbox": "local", "sandbox_machine_id": "mine"}, "owner"
    )
    assert result["sandbox_machine_id"] == "mine"
    machines.assert_awaited_with("owner", include_offline=True)


async def test_bad_environment_value_is_not_echoed_by_api_error():
    with pytest.raises(AppError) as error:
        await validate_runtime_configuration({"env_vars": {"KEY": "secret\x00"}}, "owner")
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("list_type", [False, True])
async def test_channel_lists_do_not_leak_runtime_secrets(monkeypatch, list_type):
    storage = ChannelStorage()
    config = {
        "user_id": "owner",
        "channel_type": "telegram",
        "instance_id": "instance",
        "runtime_config": {"env_vars": {"API_KEY": "sensitive-value"}},
    }
    for name in ("count_user_configs", "count_user_configs_by_type"):
        monkeypatch.setattr(storage, name, AsyncMock(return_value=1))
    for name in ("list_user_configs", "list_user_configs_by_type"):
        monkeypatch.setattr(storage, name, AsyncMock(return_value=[config]))
    user = TokenPayload(sub="owner", username="test")
    result = (
        await channels.list_channel_instances(ChannelType.TELEGRAM, user, storage)
        if list_type
        else await channels.list_user_channels(user, storage)
    )
    assert "sensitive-value" not in result.model_dump_json()
    assert result.channels[0].runtime_config["env_vars"] == {"API_KEY": "***"}
