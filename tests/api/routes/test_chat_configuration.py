import pytest

from src.api.routes.chat_configuration import validate_chat_configuration
from src.infra.channel.registry import get_registry
from src.kernel.errors import AppError
from src.kernel.schemas.channel import ChannelType


def test_invalid_secret_is_rejected_without_echoing_it():
    secret = "sensitive-secret\nvalue"
    with pytest.raises(AppError) as result:
        validate_chat_configuration(
            get_registry(),
            ChannelType.WEBHOOK,
            {"webhook_secret": secret, "allowed_sender_ids": "1"},
        )
    assert secret not in str(result.value)


def test_chat_mode_requires_credentials_and_an_allowlist():
    for config in [{"receive_enabled": True}, {"receive_enabled": True, "bot_token": "token"}]:
        with pytest.raises(AppError):
            validate_chat_configuration(get_registry(), ChannelType.TELEGRAM, config)


def test_legacy_outbound_config_remains_valid():
    config = {"webhook_url": "https://hooks.slack.com/example"}
    validate_chat_configuration(get_registry(), ChannelType.SLACK, config)
    assert config["receive_enabled"] is False


def test_generic_webhook_default_receiving_is_persisted():
    config = {"webhook_secret": "a-strong-test-secret", "allowed_sender_ids": "user"}
    validate_chat_configuration(get_registry(), ChannelType.WEBHOOK, config)
    assert config["receive_enabled"] is True
