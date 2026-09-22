"""Feishu reaction, text, card, and message patch operations."""

import json
from typing import Any

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger

logger = get_logger(__name__)


async def _json_dumps_text_body(content: str) -> str:
    return await run_long_blocking_io(json.dumps, {"text": content}, ensure_ascii=False)


class FeishuMessageSenderMixin:
    """Mixin providing message send/update and reaction operations."""

    _client: Any
    _resolve_receive_id: Any
    _REPLY_FALLBACK_ERROR_CODES: set[int]

    def _add_reaction_sync(self, message_id: str, emoji_type: str) -> str | None:
        """Sync helper for adding reaction."""
        from lark_oapi.api.im.v1 import (
            CreateMessageReactionRequest,
            CreateMessageReactionRequestBody,
            Emoji,
        )

        try:
            request = (
                CreateMessageReactionRequest.builder()
                .message_id(message_id)
                .request_body(
                    CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
                    .build()
                )
                .build()
            )

            response = self._client.im.v1.message_reaction.create(request)

            if not response.success():
                logger.warning(f"Failed to add reaction: code={response.code}, msg={response.msg}")
                return None
            data = response.data
            return data.reaction_id if data else None
        except Exception as e:
            logger.warning(f"Error adding reaction: {e}")
            return None

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP") -> str | None:
        """Add a reaction emoji to a message."""
        if not self._client:
            return None

        return await run_long_blocking_io(self._add_reaction_sync, message_id, emoji_type)

    def _delete_reaction_sync(self, message_id: str, reaction_id: str) -> bool:
        """Sync helper for deleting reaction."""
        from lark_oapi.api.im.v1 import DeleteMessageReactionRequest

        try:
            request = (
                DeleteMessageReactionRequest.builder()
                .message_id(message_id)
                .reaction_id(reaction_id)
                .build()
            )
            response = self._client.im.v1.message_reaction.delete(request)
            if not response.success():
                logger.warning(
                    f"Failed to delete reaction: code={response.code}, msg={response.msg}"
                )
                return False
            return True
        except Exception as e:
            logger.warning(f"Error deleting reaction: {e}")
            return False

    async def _delete_reaction(self, message_id: str, reaction_id: str) -> bool:
        """Delete a reaction emoji from a message."""
        if not self._client:
            return False

        return await run_long_blocking_io(self._delete_reaction_sync, message_id, reaction_id)

    def _send_message_sync(
        self, receive_id_type: str, receive_id: str, msg_type: str, content: str
    ) -> bool:
        """Send a message synchronously."""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type(msg_type)
                    .content(content)
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if not response.success():
                logger.error(
                    f"Failed to send Feishu {msg_type} message: code={response.code}, msg={response.msg}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Error sending Feishu {msg_type} message: {e}")
            return False

    async def send_message(self, chat_id: str, content: str, **kwargs: Any) -> bool:
        """Send a text message to a chat."""
        if not self._client:
            return False

        receive_id_type, receive_id = self._resolve_receive_id(chat_id)
        text_body = await _json_dumps_text_body(content)

        return await run_long_blocking_io(
            self._send_message_sync, receive_id_type, receive_id, "text", text_body
        )

    def _send_message_with_id_sync(
        self, receive_id_type: str, receive_id: str, msg_type: str, content: str
    ) -> tuple[bool, str | None]:
        """Send a message synchronously and return (success, message_id)."""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type(msg_type)
                    .content(content)
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if not response.success():
                logger.error(
                    f"Failed to send Feishu {msg_type} message: code={response.code}, msg={response.msg}"
                )
                return False, None
            # Return message_id (response.data is an attribute, not a method)
            data = response.data
            message_id = data.message_id if data else None
            return True, message_id
        except Exception as e:
            logger.error(f"Error sending Feishu {msg_type} message: {e}")
            return False, None

    async def send_message_with_id(self, chat_id: str, content: str) -> tuple[bool, str | None]:
        """Send a text message and return (success, message_id)."""
        if not self._client:
            return False, None

        receive_id_type, receive_id = self._resolve_receive_id(chat_id)
        text_body = await _json_dumps_text_body(content)

        return await run_long_blocking_io(
            self._send_message_with_id_sync, receive_id_type, receive_id, "text", text_body
        )

    def _send_card_message_sync(
        self,
        receive_id_type: str,
        receive_id: str,
        card_content: str,
        reply_to_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Send a card message synchronously and return (success, message_id).

        Args:
            receive_id_type: Type of receive_id (chat_id, open_id, etc.)
            receive_id: The target ID
            card_content: JSON string of the card content
            reply_to_id: Optional message ID to reply to (for quote/reply)
        """
        try:
            via = "create"
            # Use ReplyMessageRequest API for replies
            if reply_to_id:
                from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

                request = (
                    ReplyMessageRequest.builder()
                    .message_id(reply_to_id)
                    .request_body(
                        ReplyMessageRequestBody.builder()
                        .msg_type("interactive")
                        .content(card_content)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.message.reply(request)

                if not response.success():
                    logger.warning(
                        "Reply Feishu card failed: code=%s msg=%s receive_id_type=%s receive_id=%s",
                        response.code,
                        response.msg,
                        receive_id_type,
                        receive_id,
                    )
                    if response.code in self._REPLY_FALLBACK_ERROR_CODES:
                        logger.info(
                            "Falling back to create Feishu card after reply failure: "
                            "code=%s receive_id_type=%s receive_id=%s",
                            response.code,
                            receive_id_type,
                            receive_id,
                        )
                        from lark_oapi.api.im.v1 import (
                            CreateMessageRequest,
                            CreateMessageRequestBody,
                        )

                        request = (
                            CreateMessageRequest.builder()
                            .receive_id_type(receive_id_type)
                            .request_body(
                                CreateMessageRequestBody.builder()
                                .receive_id(receive_id)
                                .msg_type("interactive")
                                .content(card_content)
                                .build()
                            )
                            .build()
                        )
                        response = self._client.im.v1.message.create(request)
                        via = "reply-fallback"
                else:
                    via = "reply"
            else:
                # Use CreateMessageRequest API for new messages
                from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

                request = (
                    CreateMessageRequest.builder()
                    .receive_id_type(receive_id_type)
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(receive_id)
                        .msg_type("interactive")
                        .content(card_content)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.message.create(request)
                via = "create"

            if not response.success():
                logger.error(
                    "Failed to send Feishu card message: code=%s, msg=%s, "
                    "receive_id_type=%s, receive_id=%s",
                    response.code,
                    response.msg,
                    receive_id_type,
                    receive_id,
                )
                return False, None
            data = response.data
            message_id = data.message_id if data else None
            logger.info("[Feishu] Card delivered message_id=%s via=%s", message_id, via)
            return True, message_id
        except Exception as e:
            logger.error(f"Error sending Feishu card message: {e}")
            return False, None

    async def _send_card_message_internal(
        self,
        receive_id_type: str,
        receive_id: str,
        card_content: str,
        reply_to_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Send a card message and return (success, message_id).

        Args:
            receive_id_type: Type of receive_id
            receive_id: The target ID
            card_content: JSON string of the card content
            reply_to_id: Optional message ID to reply to
        """
        if not self._client:
            return False, None

        return await run_long_blocking_io(
            self._send_card_message_sync,
            receive_id_type,
            receive_id,
            card_content,
            reply_to_id,
        )

    async def send_card_message(
        self, chat_id: str, card_content: str, reply_to_id: str | None = None
    ) -> bool:
        """Send a card message to a chat.

        Args:
            chat_id: Chat ID or open_id
            card_content: JSON string of the card content
            reply_to_id: Optional message ID to reply to (for quote/reply)
        """
        if not self._client:
            return False

        receive_id_type, receive_id = self._resolve_receive_id(chat_id)
        success, _ = await self._send_card_message_internal(
            receive_id_type, receive_id, card_content, reply_to_id
        )
        return success

    def _patch_message_sync(self, message_id: str, content: str) -> bool:
        """Patch/update a message synchronously. Only works for card messages."""
        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody

        try:
            request = (
                PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(PatchMessageRequestBody.builder().content(content).build())
                .build()
            )
            response = self._client.im.v1.message.patch(request)
            if not response.success():
                logger.debug(
                    f"Failed to patch Feishu message (may not be a card): code={response.code}"
                )
                return False
            return True
        except Exception as e:
            logger.debug(f"Error patching Feishu message: {e}")
            return False

    def _update_text_message_sync(self, message_id: str, content: str) -> bool:
        """Update a text message using the update API."""
        from lark_oapi.api.im.v1 import UpdateMessageRequest, UpdateMessageRequestBody

        try:
            text_body = json.dumps({"text": content}, ensure_ascii=False)
            request = (
                UpdateMessageRequest.builder()
                .message_id(message_id)
                .request_body(UpdateMessageRequestBody.builder().content(text_body).build())
                .build()
            )
            response = self._client.im.v1.message.update(request)
            if not response.success():
                logger.debug(f"Failed to update Feishu text message: code={response.code}")
                return False
            return True
        except Exception as e:
            logger.debug(f"Error updating Feishu text message: {e}")
            return False

    async def patch_message(self, message_id: str, content: str) -> bool:
        """Update an existing message's content. Tries update API first, then patch."""
        if not self._client:
            return False

        # Try update API first (for text messages)
        success = await run_long_blocking_io(self._update_text_message_sync, message_id, content)
        if success:
            return True

        # Fall back to patch API (for card messages only)
        text_body = await _json_dumps_text_body(content)
        return await run_long_blocking_io(self._patch_message_sync, message_id, text_body)

    async def patch_card_message(self, message_id: str, card_content: str) -> bool:
        """Patch/update an existing interactive card message."""
        if not self._client:
            return False
        return await run_long_blocking_io(self._patch_message_sync, message_id, card_content)
