from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.deps import get_current_user_required
from src.api.error_handlers import register_error_handlers
from src.api.routes import feedback
from src.infra.feedback.manager import FeedbackManager
from src.infra.feedback.storage import FeedbackStorage
from src.kernel.schemas.feedback import FeedbackStats
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize(
    "permissions,requested,expected",
    [
        (["feedback:write"], None, "owner"),
        (["feedback:write"], "another-user", "owner"),
        (["feedback:read"], "another-user", "another-user"),
        (["feedback:read"], None, None),
        ([], None, None),
    ],
)
async def test_feedback_list_scopes_items_counts_and_stats_to_authorized_user(
    permissions, requested, expected
):
    manager = FeedbackManager()
    storage = SimpleNamespace(
        list=AsyncMock(return_value=[]),
        count=AsyncMock(return_value=0),
        get_stats=AsyncMock(return_value=FeedbackStats()),
    )
    manager.storage = storage
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(feedback.router, prefix="/feedback")
    app.dependency_overrides[get_current_user_required] = lambda: TokenPayload(
        sub="owner", username="owner", permissions=permissions
    )
    app.dependency_overrides[feedback.get_feedback_manager] = lambda: manager
    params = {"session_id": "session"}
    if requested is not None:
        params["user_id"] = requested
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/feedback/", params=params)
    if not permissions:
        assert response.status_code == 403
        storage.list.assert_not_called()
        storage.count.assert_not_called()
        storage.get_stats.assert_not_called()
    else:
        assert response.status_code == 200
        storage.list.assert_awaited_once_with(0, 50, None, expected, "session")
        storage.count.assert_awaited_once_with(None, expected, "session")
        storage.get_stats.assert_awaited_once_with("session", None, expected)


async def test_feedback_stats_query_keeps_owner_filter():
    storage = FeedbackStorage()
    collection = SimpleNamespace(
        aggregate=AsyncMock(return_value=SimpleNamespace(to_list=AsyncMock(return_value=[])))
    )
    storage._collection = collection
    await storage.get_stats("session", user_id="owner")
    assert collection.aggregate.call_args.args[0][0] == {
        "$match": {"session_id": "session", "user_id": "owner"}
    }
