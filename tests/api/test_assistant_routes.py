"""Assistant API uses existing authentication and never accepts owner credentials."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps
from src.api.error_handlers import register_error_handlers
from src.infra.utils.datetime import utc_now
from src.kernel.schemas.assistant import Assistant, AssistantActivity
from src.kernel.schemas.user import TokenPayload


@pytest.fixture
def api(monkeypatch):
    from src.api.routes import assistants
    from src.infra.task.background_task_store import BackgroundTaskStore

    task_collection = SimpleNamespace(find_one=AsyncMock(return_value=None))
    monkeypatch.setattr(BackgroundTaskStore, "collection", property(lambda self: task_collection))
    now = utc_now()
    value = Assistant(
        id="a",
        session_id="s",
        name="Helper",
        user_id="owner",
        revision=1,
        status="active",
        created_at=now,
        updated_at=now,
    )
    store = SimpleNamespace(list=AsyncMock(return_value=[value]), count=AsyncMock(return_value=7))
    service = SimpleNamespace(
        store=store,
        create=AsyncMock(return_value=value),
        get=AsyncMock(return_value=value),
        update=AsyncMock(return_value=value),
    )
    monkeypatch.setattr(assistants, "_service", lambda: service)
    service.activity = AsyncMock(
        return_value={
            "a": AssistantActivity(
                **{
                    "state": "waiting_human",
                    "session_id": "approval-chat",
                    "preview": "Review plan",
                    "updated_at": now,
                    "unread_count": 1,
                }
            )
        }
    )
    monkeypatch.setattr(assistants, "load_assistant_activity", service.activity, raising=False)
    service.task_collection = task_collection
    service.tasks = SimpleNamespace(
        list=AsyncMock(return_value={"tasks": [], "total": 0, "skip": 0, "limit": 20}),
        create=AsyncMock(
            return_value={"task_id": "task", "session_id": "child", "status": "queued"}
        ),
        review=AsyncMock(return_value={"id": "task", "state": "accepted"}),
    )
    monkeypatch.setattr(assistants, "_task_service", lambda: service.tasks, raising=False)
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(assistants.router, prefix="/api/assistants")
    account = TokenPayload(
        sub="owner", username="owner", roles=["user"], permissions=["session:read", "chat:write"]
    )
    app.dependency_overrides[deps.get_current_user_required] = lambda: account
    return app, service, account


async def test_list_returns_total_and_owner_scoped_page(api):
    app, service, _ = api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/assistants?skip=2&limit=5")
    assert response.status_code == 200
    assert response.json()["total"] == 7
    service.store.list.assert_awaited_once_with("owner", skip=2, limit=5, archived=False)


async def test_create_uses_authenticated_owner(api):
    app, service, account = api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/assistants", json={"name": "Helper"})
    assert response.status_code == 201
    assert service.create.call_args.args[0] is account
    assert response.json()["session_id"] == "s"


@pytest.mark.parametrize(
    "extra", [{"user_id": "victim"}, {"api_key": "secret"}, {"session_id": "victim-session"}]
)
async def test_create_refuses_injected_identity_and_credentials(api, extra):
    app, service, _ = api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/assistants", json={"name": "Helper", **extra})
    assert response.status_code == 422
    service.create.assert_not_awaited()


async def test_read_permission_does_not_allow_configuration_writes(api):
    app, service, account = api
    account.permissions = ["session:read"]
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put("/api/assistants/a", json={"name": "Changed", "revision": 1})
    assert response.status_code == 403
    service.update.assert_not_awaited()


async def test_update_passes_revision_and_authenticated_owner(api):
    app, service, account = api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            "/api/assistants/a", json={"name": "Changed", "revision": 4, "status": "paused"}
        )
    assert response.status_code == 200
    called_user, assistant_id, data = service.update.call_args.args
    assert called_user is account and assistant_id == "a"
    assert data.revision == 4 and data.status == "paused"


async def test_invalid_page_never_reaches_storage(api):
    app, service, _ = api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/assistants?limit=10000")
    assert response.status_code == 422
    service.store.list.assert_not_awaited()


async def test_task_list_passes_owned_assistant_and_page(api):
    app, service, account = api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/assistants/a/tasks?skip=5&limit=10")
    assert response.status_code == 200
    service.tasks.list.assert_awaited_once_with(account, "a", skip=5, limit=10)


async def test_task_creation_is_real_admission_and_readers_cannot_submit(api):
    from uuid import uuid4

    app, service, account = api
    payload = {
        "description": "Save the verified result",
        "request_id": str(uuid4()),
        "timeout_seconds": 300,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/assistants/a/tasks", json=payload)
        assert response.status_code == 202
        assert response.json()["task_id"] == "task"
        account.permissions = ["session:read"]
        denied = await client.post("/api/assistants/a/tasks", json=payload)
    assert denied.status_code == 403
    assert service.tasks.create.await_count == 1


async def test_review_requires_the_observed_run_and_chat_write(api):
    app, service, account = api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.put(
            "/api/assistants/a/tasks/task/review",
            json={"run_id": "run", "accepted": True, "revision": 2},
        )
    assert response.status_code == 200
    args = service.tasks.review.call_args.args
    assert args[:3] == (account, "a", "task")
    assert args[3].run_id == "run" and args[3].revision == 2


async def test_open_returns_the_persisted_conversation(api):
    from src.kernel.schemas.session import Session

    app, service, account = api
    service.open_conversation = AsyncMock(
        return_value=Session(id="conversation", user_id="owner", metadata={"assistant_id": "a"})
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/assistants/a/conversation")
    assert response.status_code == 200
    assert response.json()["id"] == "conversation"
    service.open_conversation.assert_awaited_once_with(account, "a")


async def test_conversation_lookup_uses_canonical_owner_scoped_identity(api):
    app, service, account = api
    service.store.for_session = AsyncMock(return_value=service.get.return_value)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/assistants/conversation/owned-chat")
    assert response.status_code == 200
    assert response.json()["id"] == "a"
    service.store.for_session.assert_awaited_once_with(account.sub, "owned-chat")


async def test_unowned_or_ordinary_conversation_has_no_assistant_identity(api):
    app, service, _ = api
    service.store.for_session = AsyncMock(return_value=None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/assistants/conversation/foreign-chat")
    assert response.status_code == 200
    assert response.json() is None


async def test_discussions_are_owned_paginated_and_do_not_expose_sender(api, monkeypatch):
    from src.infra.assistant.discussions import DiscussionStore

    app, service, account = api
    rows = AsyncMock(
        return_value=(
            [
                {
                    "session_id": "group",
                    "channel_type": "feishu",
                    "chat_id": "room",
                    "created_at": utc_now(),
                    "sender_id": "private-sender",
                }
            ],
            3,
        )
    )
    monkeypatch.setattr(DiscussionStore, "list", rows, raising=False)
    monkeypatch.setattr(
        "src.infra.assistant.discussions.validate_discussion",
        AsyncMock(return_value=service.get.return_value),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/assistants/a/discussions?skip=2&limit=5")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3 and body["discussions"][0]["available"] is True
    assert "sender_id" not in body["discussions"][0]
    service.get.assert_awaited_once_with(account, "a")
    rows.assert_awaited_once_with("owner", "a", skip=2, limit=5)


async def test_rule_creation_requires_schedule_permission_and_binds_owned_assistant(
    api, monkeypatch
):
    from src.infra.scheduler.service import ScheduledTaskService

    app, service, account = api
    create = AsyncMock(return_value=SimpleNamespace(id="schedule"))
    monkeypatch.setattr(ScheduledTaskService, "create_task", create)
    service.validate_configuration = AsyncMock()
    data = {
        "name": "Watch",
        "instructions": "Check for changes",
        "mode": "observe",
        "interval_seconds": 60,
        "timeout_seconds": 120,
        "max_wakeups": 3,
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post("/api/assistants/a/rules", json=data)
        assert denied.status_code == 403
        account.permissions.append("scheduled_task:write")
        response = await client.post("/api/assistants/a/rules", json=data)
    assert response.status_code == 201
    request = create.call_args.args[0]
    assert request.input_payload["assistant_rule"]["assistant_id"] == "a"
    assert request.input_payload["assistant_rule"]["mode"] == "observe"
    assert request.max_retries == 0 and request.run_on_start is False
    create.assert_awaited_once()


async def test_background_task_identity_uses_owned_task_and_its_original_audience(api, monkeypatch):
    app, service, _ = api
    service.store.for_session = AsyncMock(return_value=None)
    service.store.get = AsyncMock(return_value=service.get.return_value)
    service.task_collection.find_one.return_value = {
        "_id": "owned-task",
        "assistant_id": "a",
        "parent_session_id": "parent",
        "assistant_source_session_id": "audience",
        "config": {"model_id": "original"},
    }
    discussion = AsyncMock(return_value=None)
    monkeypatch.setattr("src.infra.assistant.discussions.task_discussion", discussion)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/assistants/conversation/child")
    assert response.status_code == 200
    assert response.json()["context_kind"] == "task"
    assert response.json()["context_task_id"] == "owned-task"
    assert response.json()["context_session_id"] == "audience"
    service.task_collection.find_one.assert_awaited_once_with(
        {"user_id": "owner", "session_id": "child"}
    )
    service.store.get.assert_awaited_once_with("owner", "a")
    discussion.assert_awaited_once()


async def test_list_exposes_real_activity_for_only_the_visible_owned_assistants(api):
    app, service, _ = api
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/assistants")
    row = response.json()["assistants"][0]
    assert row["activity"]["state"] == "waiting_human"
    assert row["activity"]["session_id"] == "approval-chat"
    service.activity.assert_awaited_once_with("owner", ["a"])
