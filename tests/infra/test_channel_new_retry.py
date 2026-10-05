"""A failed /new confirmation must not rotate the conversation again on replay."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


async def test_new_session_identity_is_stable_for_retried_delivery():
    from src.infra.channel.inbox_worker import current_delivery
    from src.infra.channel.session_scope import new_delivery_session

    checkpoint = {}

    async def save(**values):
        checkpoint.update(values)

    token = current_delivery.set(SimpleNamespace(checkpoint=checkpoint, save=save))
    try:
        first = await new_delivery_session("weixin_scope")
        second = await new_delivery_session("weixin_scope")
        assert first == second
        assert first == checkpoint["new_session_id"]
    finally:
        current_delivery.reset(token)


async def test_feishu_new_confirmation_failure_keeps_delivery_pending(monkeypatch):
    from src.infra.channel.feishu import handler as module
    from src.infra.channel.inbox_worker import current_delivery

    monkeypatch.setattr(module, "_create_new_feishu_session", AsyncMock(return_value="new"))
    manager = SimpleNamespace(send_message=AsyncMock(return_value=False))
    handle = module.create_feishu_message_handler(manager, "fast")
    token = current_delivery.set(SimpleNamespace(checkpoint={}, save=AsyncMock()))
    try:
        with pytest.raises(RuntimeError, match="reply"):
            await handle("owner", "sender", "chat", "/new", {})
    finally:
        current_delivery.reset(token)
