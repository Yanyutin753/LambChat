"""Read runtime activity for the visible, owner-scoped companion roster."""

from src.infra.session.storage import SessionStorage
from src.kernel.schemas.assistant import AssistantActivity


async def load_assistant_activity(
    user_id: str, assistant_ids: list[str]
) -> dict[str, AssistantActivity]:
    if not assistant_ids:
        return {}
    storage = SessionStorage()
    await storage.ensure_indexes_if_needed()
    pipeline = [
        {
            "$match": {
                "user_id": user_id,
                "is_active": {"$ne": False},
                "$or": [
                    {"metadata.assistant_id": {"$in": assistant_ids}},
                    {"metadata.background_assistant_id": {"$in": assistant_ids}},
                ],
                "metadata.task_status": {
                    "$in": [
                        "waiting_human",
                        "running",
                        "starting",
                        "pending",
                        "queued",
                        "recovering",
                        "cancelling",
                        "completed",
                        "failed",
                        "cancelled",
                        "expired",
                    ]
                },
            }
        },
        {
            "$project": {
                "assistant_id": {
                    "$ifNull": ["$metadata.assistant_id", "$metadata.background_assistant_id"]
                },
                "session_id": {"$ifNull": ["$session_id", {"$toString": "$_id"}]},
                "state": "$metadata.task_status",
                "preview": {"$substrCP": [{"$ifNull": ["$latest_user_message", "$name"]}, 0, 160]},
                "updated_at": 1,
                "unread_count": {"$ifNull": ["$unread_count", 0]},
                # Live work wins over history; among terminal runs the latest result wins.
                "priority": {
                    "$switch": {
                        "branches": [
                            {
                                "case": {"$eq": ["$metadata.task_status", "waiting_human"]},
                                "then": 2,
                            },
                            {
                                "case": {
                                    "$in": [
                                        "$metadata.task_status",
                                        [
                                            "running",
                                            "starting",
                                            "pending",
                                            "queued",
                                            "recovering",
                                            "cancelling",
                                        ],
                                    ]
                                },
                                "then": 1,
                            },
                        ],
                        "default": 0,
                    }
                },
            }
        },
        {"$sort": {"priority": -1, "updated_at": -1, "_id": -1}},
        {"$group": {"_id": "$assistant_id", "activity": {"$first": "$$ROOT"}}},
    ]
    result = {}
    async for row in await storage.collection.aggregate(pipeline):
        if row["_id"] in assistant_ids:
            result[row["_id"]] = AssistantActivity.model_validate(row["activity"])
    return result
