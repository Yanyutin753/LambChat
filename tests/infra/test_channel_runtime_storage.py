from unittest.mock import AsyncMock

from src.infra.channel.channel_storage import ChannelStorage
from src.kernel.schemas.channel import ChannelType


async def test_runtime_secrets_round_trip_encrypted_and_masked_in_both_response_locations(
    monkeypatch,
):
    storage = ChannelStorage()
    monkeypatch.setattr(storage, "ensure_indexes_if_needed", AsyncMock())
    collection = AsyncMock()
    monkeypatch.setattr(storage, "_get_collection", lambda: collection)
    runtime = {"sandbox": "local", "env_vars": {"API_KEY": "sensitive-value"}}
    config = await storage.create_config(
        "owner", ChannelType.TELEGRAM, {}, "test", runtime_config=runtime
    )
    stored = collection.insert_one.call_args.args[0]
    assert "sensitive-value" not in repr(stored)
    assert config["runtime_config"] == runtime
    response = storage.build_response_from_config(config, ChannelType.TELEGRAM, "owner")
    assert response.runtime_config["env_vars"] == {"API_KEY": "***"}
    assert "sensitive-value" not in response.model_dump_json()


async def test_nested_provider_config_cannot_override_authoritative_runtime_settings():
    storage = ChannelStorage()
    config = await storage._doc_to_config(
        {
            "user_id": "owner",
            "channel_type": "telegram",
            "config": {"runtime_config": {"env_vars": {"SPOOF": "x"}}},
        }
    )
    assert config["runtime_config"] == {}
