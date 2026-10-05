"""Validate receiving configuration before persisting credentials or starting bots."""

from typing import Any

from pydantic import ValidationError

from src.infra.channel.chat import ChatConfig
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.channel import ChannelType


def validate_chat_configuration(registry: Any, channel_type: ChannelType, config: dict) -> None:
    manager = registry.get_manager_class(channel_type)
    model = getattr(manager, "config_class", None)
    if not isinstance(model, type) or not issubclass(model, ChatConfig):
        return
    try:
        validated = model(**config)
        channel = manager.channel_class(validated)
        if validated.receive_enabled and (
            not channel._validate_inbound_config()
            or not (
                validated.allowed_sender_ids.strip()
                or validated.allowed_chat_ids.strip()
                or validated.default_chat_id.strip()
            )
        ):
            raise ValueError("Incomplete receiving configuration")
    except (ValidationError, ValueError, TypeError):
        # Pydantic errors can include credential values. Never return or log them.
        raise AppError(ErrorCode.VALIDATION_ERROR) from None
    config["receive_enabled"] = validated.receive_enabled
