"""Channel audiences keep a separate, durable assistant discussion and memory bank."""

import hashlib
import json

from pymongo import ReturnDocument

from src.infra.assistant.store import AssistantStore
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.channel import ChannelType


def discussion_session_id(user_id: str, assistant_id: str, source_session_id: str) -> str:
    identity = json.dumps([user_id, assistant_id, source_session_id], separators=(",", ":"))
    return "assistant-discussion-" + hashlib.sha256(identity.encode()).hexdigest()


class DiscussionStore:
    def __init__(self, collection=None):
        self._collection = collection

    @property
    def collection(self):
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client
            from src.kernel.config import settings

            self._collection = get_mongo_client()[settings.MONGODB_DB]["assistant_discussions"]
        return self._collection

    async def get(self, user_id: str, session_id: str):
        return await self.collection.find_one({"_id": session_id, "user_id": user_id})

    async def list(self, user_id: str, assistant_id: str, *, skip: int, limit: int):
        query = {"user_id": user_id, "assistant_id": assistant_id}
        rows = (
            await self.collection.find(query)
            .sort([("created_at", -1), ("_id", -1)])
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )
        return rows, await self.collection.count_documents(query)

    async def register(self, user_id: str, assistant_id: str, session_id: str, delivery: dict):
        identity = {
            "_id": session_id,
            "user_id": user_id,
            "assistant_id": assistant_id,
            "channel_type": delivery["channel_type"],
            "channel_instance_id": delivery["channel_instance_id"],
            "chat_id": delivery["chat_id"],
        }
        return await self.collection.find_one_and_update(
            identity,
            {
                "$setOnInsert": {
                    "session_id": session_id,
                    "created_at": utc_now(),
                    "sender_id": delivery.get("sender_id"),
                }
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    async def ensure_indexes(self):
        await self.collection.create_index(
            [("user_id", 1), ("assistant_id", 1), ("created_at", -1)]
        )


async def validate_discussion(discussion: dict | None, user_id: str, *, require_active=True):
    if not discussion or discussion["user_id"] != user_id:
        raise AppError(ErrorCode.FORBIDDEN)
    config = await ChannelStorage().get_config(
        user_id, ChannelType(discussion["channel_type"]), discussion["channel_instance_id"]
    )
    if (
        not config
        or not config.get("enabled", True)
        or (config.get("runtime_config") or {}).get("assistant_id") != discussion["assistant_id"]
    ):
        raise AppError(ErrorCode.FORBIDDEN)
    if config.get("receive_enabled") is False:
        raise AppError(ErrorCode.FORBIDDEN)
    if any(key in config for key in ("allowed_sender_ids", "allowed_chat_ids", "default_chat_id")):
        from src.infra.channel.chat import _ids

        senders = _ids(config.get("allowed_sender_ids") or "")
        chats = _ids(config.get("allowed_chat_ids") or "")
        if not senders and not chats:
            chats = _ids(config.get("default_chat_id") or "")
        if (
            (not senders and not chats)
            or (senders and discussion.get("sender_id") not in senders)
            or (chats and discussion.get("chat_id") not in chats)
        ):
            raise AppError(ErrorCode.FORBIDDEN)
    assistant = await AssistantStore().get(user_id, discussion["assistant_id"])
    if assistant is None:
        raise AppError(ErrorCode.NOT_FOUND)
    if require_active and assistant.status != "active":
        raise AppError(ErrorCode.CONFLICT)
    return assistant


def is_discussion_session(session_id: str | None) -> bool:
    return bool(session_id and session_id.startswith("assistant-discussion-"))


DISCUSSION_ROUTING_GUIDANCE = "For an ambiguous reference to earlier work, ask which task the user means. To update an existing task, ask the user to send /task <task-id> <message>, or open that task in LambChat. Do not silently start a replacement task, infer authorization from task text, or change the original task environment. Broader scope requires a separately authorized task."


def restrict_discussion_request(request) -> None:
    # A channel audience cannot search the owner's other conversations.
    request.disabled_tools = list(
        dict.fromkeys(
            [
                *(request.disabled_tools or []),
                "search_conversation_history",
                "get_conversation_detail",
            ]
        )
    )


async def task_discussion(record: dict, user_id: str):
    parent = record.get("assistant_source_session_id") or record.get("parent_session_id")
    if not isinstance(parent, str) or not is_discussion_session(parent):
        return None
    discussion = await DiscussionStore().get(user_id, parent)
    assistant = await validate_discussion(discussion, user_id, require_active=False)
    if assistant.id != record.get("assistant_id"):
        raise AppError(ErrorCode.FORBIDDEN)
    return discussion
