from unittest.mock import AsyncMock

import pytest

from src.infra.channel.telegram import TelegramChannel, TelegramConfig, parse_telegram_update


def update(**changes):
    message = {
        "message_id": 7,
        "text": "hello",
        "chat": {"id": 123, "type": "private"},
        "from": {"id": 42, "is_bot": False},
    }
    message.update(changes)
    return {"update_id": 9, "message": message}


def test_parse_private_message_and_topic_context():
    parsed = parse_telegram_update(update(message_thread_id=11), "lambbot")
    assert parsed["sender_id"] == "42"
    assert parsed["chat_id"] == "123"
    assert parsed["message_id"] == "123:7"
    assert parsed["metadata"]["message_thread_id"] == 11


def test_ignore_bots_and_unmentioned_groups():
    assert parse_telegram_update(update(**{"from": {"id": 4, "is_bot": True}}), "lambbot") is None
    assert parse_telegram_update(update(chat={"id": -1, "type": "group"}), "lambbot") is None
    result = parse_telegram_update(
        update(text="@lambbot hello", chat={"id": -1, "type": "group"}), "lambbot"
    )
    assert result["content"] == "hello"


def test_group_mentions_must_match_complete_bot_username():
    assert (
        parse_telegram_update(
            update(text="@lambbot_other hello", chat={"id": -1, "type": "group"}), "lambbot"
        )
        is None
    )
    result = parse_telegram_update(
        update(text="/new@LambBot", chat={"id": -1, "type": "group"}), "lambbot"
    )
    assert result["content"] == "/new"


async def test_failed_agent_run_does_not_advance_poll_cursor():
    ch = TelegramChannel(TelegramConfig(bot_token="token"))
    ch._bot_username = "lambbot"
    ch._api = AsyncMock(return_value=[update()])
    ch.enqueue_inbound = AsyncMock(return_value=True)
    ch.drain = AsyncMock(return_value=False)
    storage = AsyncMock()
    storage.get.return_value = None
    with pytest.raises(RuntimeError):
        await ch._poll_once(storage)
    storage.set.assert_not_called()


async def test_failed_dispatch_does_not_advance_poll_cursor():
    ch = TelegramChannel(TelegramConfig(bot_token="token"))
    ch._bot_username = "lambbot"
    ch._api = AsyncMock(return_value=[update()])
    ch.enqueue_inbound = AsyncMock(return_value=False)
    storage = AsyncMock()
    storage.get.return_value = None
    with pytest.raises(RuntimeError):
        await ch._poll_once(storage)
    storage.set.assert_not_called()


async def test_successful_dispatch_advances_poll_cursor():
    ch = TelegramChannel(TelegramConfig(bot_token="token"))
    ch._bot_username = "lambbot"
    ch._api = AsyncMock(return_value=[update()])
    ch.enqueue_inbound = AsyncMock(return_value=True)
    ch.drain = AsyncMock(return_value=True)
    storage = AsyncMock()
    storage.get.return_value = None
    await ch._poll_once(storage)
    assert storage.set.call_args.args[1] == 10


async def test_existing_webhook_is_never_deleted_implicitly():
    from src.infra.channel.chat import InboundConfigurationError

    ch = TelegramChannel(TelegramConfig(bot_token="token"))
    ch._api = AsyncMock(
        side_effect=[{"id": 1, "username": "lambbot"}, {"url": "https://existing.example"}]
    )
    with pytest.raises(InboundConfigurationError):
        await ch._run_inbound()
    assert [call.args[0] for call in ch._api.call_args_list] == ["getMe", "getWebhookInfo"]


async def test_reply_is_split_without_losing_text_or_using_markup():
    ch = TelegramChannel(TelegramConfig(bot_token="token", receive_enabled=True, parse_mode="HTML"))
    ch._api = AsyncMock(return_value={"message_id": 1})
    text = "<>" * 3000
    assert await ch._send_reply("123", text, message_thread_id=9)
    payloads = [call.args[1] for call in ch._api.call_args_list]
    assert "".join(p["text"] for p in payloads) == text
    assert all("parse_mode" not in p for p in payloads)
    assert all(p["message_thread_id"] == 9 for p in payloads)
