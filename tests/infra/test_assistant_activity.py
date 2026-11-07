from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.assistant.activity import load_assistant_activity
from src.infra.session.storage import SessionStorage
from src.infra.utils.datetime import utc_now


async def test_activity_is_batched_owner_scoped_and_keeps_custom_session_ids(monkeypatch):
    async def rows():
        for assistant_id in ["visible", "other-owner"]:
            yield {
                "_id": assistant_id,
                "activity": {
                    "session_id": "custom-thread",
                    "state": "waiting_human",
                    "updated_at": utc_now(),
                    "preview": "Verify the proposal",
                    "unread_count": 2,
                },
            }

    collection = SimpleNamespace(aggregate=AsyncMock(return_value=rows()))
    monkeypatch.setattr(SessionStorage, "collection", property(lambda _: collection))
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", AsyncMock())
    result = await load_assistant_activity("owner", ["visible"])
    assert list(result) == ["visible"]
    assert result["visible"].session_id == "custom-thread"
    assert result["visible"].state == "waiting_human"
    pipeline = collection.aggregate.call_args.args[0]
    assert pipeline[0]["$match"]["user_id"] == "owner"
    assert pipeline[0]["$match"]["$or"] == [
        {"metadata.assistant_id": {"$in": ["visible"]}},
        {"metadata.background_assistant_id": {"$in": ["visible"]}},
    ]
    assert pipeline[2]["$sort"] == {"priority": -1, "updated_at": -1, "_id": -1}


async def test_empty_roster_never_queries_other_assistants(monkeypatch):
    ensure = AsyncMock()
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", ensure)
    assert await load_assistant_activity("owner", []) == {}
    ensure.assert_not_awaited()
