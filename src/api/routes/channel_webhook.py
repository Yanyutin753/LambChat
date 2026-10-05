"""Public callback endpoint authenticated by the selected channel's own secret."""

import hmac
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError

from src.api.routes.channels import get_channel_storage
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.webhook import WebhookChannelManager, WebhookInbound
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.channel import ChannelType

router = APIRouter()
MAX_CALLBACK_BYTES = 65536


@router.post("/webhook/{instance_id}/callback", status_code=202)
async def receive_webhook(
    instance_id: str,
    request: Request,
    storage: ChannelStorage = Depends(get_channel_storage),
) -> dict[str, Any]:
    # Resolve the owner from storage. Caller-supplied IDs can only identify the
    # external actor, never the tenant whose agent/tools will run.
    if len(instance_id) > 256:
        raise AppError(ErrorCode.FORBIDDEN)
    config = await storage.get_config_by_instance(ChannelType.WEBHOOK, instance_id)
    secret = str((config or {}).get("webhook_secret") or "")
    provided = request.headers.get("x-lambchat-bot-secret", "")
    if (
        not config
        or not config.get("enabled", True)
        or not config.get("receive_enabled", True)
        or not config.get("user_id")
        or config.get("instance_id") != instance_id
        or config.get("channel_type") != ChannelType.WEBHOOK.value
        or not secret
        or not hmac.compare_digest(secret.encode("utf-8"), provided.encode("utf-8"))
    ):
        raise AppError(ErrorCode.FORBIDDEN)

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_CALLBACK_BYTES:
            raise AppError(ErrorCode.PAYLOAD_TOO_LARGE)
        body.extend(chunk)
    try:
        payload = WebhookInbound.model_validate_json(body)
    except ValidationError as exc:
        # Validation input can contain credentials; return only the stable code.
        raise AppError(ErrorCode.VALIDATION_ERROR) from exc
    if payload.bot_id and payload.bot_id != instance_id:
        raise AppError(ErrorCode.VALIDATION_ERROR)
    manager = cast(WebhookChannelManager, WebhookChannelManager.get_instance())
    accepted = await manager.receive_callback(config, payload.to_message())
    if not accepted:
        raise AppError(ErrorCode.SERVICE_UNAVAILABLE)
    return {"accepted": accepted}
