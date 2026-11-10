"""Assistant tasks reuse durable detached admission and expose only owned results."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.assistant import Assistant
from src.kernel.schemas.user import TokenPayload


def owner():
    return TokenPayload(
        sub="owner", username="owner", roles=["user"], permissions=["session:read", "chat:write"]
    )


def helper():
    return Assistant(
        id="helper",
        session_id="coordinator",
        user_id="owner",
        name="Researcher",
        instructions="Verify sources",
        revision=1,
        status="active",
        sandbox="cloud",
        created_at=utc_now(),
        updated_at=utc_now(),
    )


def record(**changes):
    return {
        "_id": "task",
        "user_id": "owner",
        "parent_session_id": "coordinator",
        "parent_run_id": "source-run",
        "call_id": "call",
        "session_id": "child",
        "run_id": "run",
        "state": "submitted",
        "description": "Research a result",
        "execution_mode": "local",
        "created_at": utc_now(),
        "config": {"api_key": "must-not-escape"},
        **changes,
    }


def child(**metadata):
    return SimpleNamespace(
        user_id="owner",
        metadata={"background_task_id": "task", "current_run_id": "run", **metadata},
    )


def service(value=None, session=None):
    from src.infra.assistant.tasks import AssistantTaskService

    collection = SimpleNamespace(
        find_one=AsyncMock(return_value=value or record()),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
    )
    background = SimpleNamespace(
        store=SimpleNamespace(collection=collection),
        sessions=SimpleNamespace(get_session=AsyncMock(return_value=session)),
    )
    assistants = SimpleNamespace(
        get=AsyncMock(return_value=helper()), validate_configuration=AsyncMock()
    )
    return AssistantTaskService(
        assistants=assistants,
        background=background,
        completions=SimpleNamespace(for_runs=AsyncMock(return_value={})),
    ), collection


async def test_task_query_is_scoped_to_owner_and_canonical_assistant_session():
    task_service, collection = service(session=child(task_status="completed"))
    result = await task_service.get(owner(), "helper", "task")
    assert result["state"] == "completed"
    assert "api_key" not in str(result)
    collection.find_one.assert_awaited_once_with(
        {
            "_id": "task",
            "user_id": "owner",
            "$or": [{"assistant_id": "helper"}, {"parent_session_id": "coordinator"}],
        }
    )


async def test_foreign_child_never_leaks_its_runtime_or_results():
    foreign = SimpleNamespace(
        user_id="someone-else", metadata={"task_status": "completed", "current_run_id": "private"}
    )
    task_service, _ = service(session=foreign)
    result = await task_service.get(owner(), "helper", "task")
    assert result["state"] == "needs_attention"
    assert "private" not in str(result)


async def test_review_is_bound_to_the_completed_run_and_fences_updates():
    from src.kernel.schemas.assistant import AssistantTaskReview

    task_service, collection = service(session=child(task_status="completed"))
    await task_service.review(
        owner(), "helper", "task", AssistantTaskReview(run_id="run", accepted=True)
    )
    query, update = collection.update_one.call_args.args
    assert query["user_id"] == "owner"
    assert query["$or"] == [{"assistant_id": "helper"}, {"parent_session_id": "coordinator"}]
    assert update["$set"]["review"]["run_id"] == "run"
    assert update["$set"]["review"]["accepted"] is True


@pytest.mark.parametrize("run_id,status", [("new-run", "completed"), ("run", "running")])
async def test_review_cannot_accept_active_or_replaced_run(run_id, status):
    from src.kernel.schemas.assistant import AssistantTaskReview

    task_service, collection = service(session=child(task_status=status, current_run_id=run_id))
    with pytest.raises(AppError) as caught:
        await task_service.review(
            owner(), "helper", "task", AssistantTaskReview(run_id="run", accepted=True)
        )
    assert caught.value.error_code == ErrorCode.CONFLICT
    collection.update_one.assert_not_awaited()


async def test_old_acceptance_does_not_accept_a_follow_up_run():
    task_service, _ = service(
        value=record(review={"run_id": "old", "accepted": True}),
        session=child(task_status="completed"),
    )
    result = await task_service.get(owner(), "helper", "task")
    assert result["state"] == "completed"


async def test_manual_task_retries_dispatch_once_and_preserve_configuration(monkeypatch):
    from src.api.routes import chat_request_config
    from src.infra.assistant.tasks import AssistantTaskService
    from src.kernel.schemas.assistant import AssistantTaskCreate

    records = {}

    async def reserve(data):
        return records.setdefault(data["_id"], data.copy())

    async def dispatch(data):
        data["state"] = "submitted"
        return {"task_id": data["_id"], "session_id": data["session_id"], "status": "running"}

    background = SimpleNamespace(
        store=SimpleNamespace(reserve=reserve), submit_reserved=AsyncMock(side_effect=dispatch)
    )
    assistants = SimpleNamespace(
        get=AsyncMock(return_value=helper()), validate_configuration=AsyncMock()
    )
    monkeypatch.setattr(chat_request_config, "resolve_persona_request", AsyncMock())
    task_service = AssistantTaskService(
        assistants=assistants,
        background=background,
        completions=SimpleNamespace(for_runs=AsyncMock(return_value={})),
    )
    payload = AssistantTaskCreate(
        request_id=str(uuid4()), description="Compute and save a result", timeout_seconds=300
    )
    first = await task_service.create(owner(), "helper", payload, language="en")
    second = await task_service.create(owner(), "helper", payload, language="en")
    assert first["task_id"] == second["task_id"]
    assert len(records) == 1
    saved = next(iter(records.values()))
    assert saved["agent_options"] == {"sandbox": "cloud"}
    assert saved["authorization"]["kind"] == "user"
    assert saved["assistant_instructions"] == "Verify sources"
    assert saved["timeout_seconds"] == 300
    assert saved["session_id"] != "coordinator"


async def test_idempotency_key_cannot_be_reused_for_different_instructions(monkeypatch):
    from src.api.routes import chat_request_config
    from src.infra.assistant.tasks import AssistantTaskService
    from src.kernel.schemas.assistant import AssistantTaskCreate

    background = SimpleNamespace(
        store=SimpleNamespace(
            reserve=AsyncMock(
                return_value=record(input={"description": "original", "timeout_seconds": 300})
            )
        ),
        submit_reserved=AsyncMock(),
    )
    assistants = SimpleNamespace(
        get=AsyncMock(return_value=helper()), validate_configuration=AsyncMock()
    )
    monkeypatch.setattr(chat_request_config, "resolve_persona_request", AsyncMock())
    task_service = AssistantTaskService(
        assistants=assistants,
        background=background,
        completions=SimpleNamespace(for_runs=AsyncMock(return_value={})),
    )
    with pytest.raises(AppError) as caught:
        await task_service.create(
            owner(),
            "helper",
            AssistantTaskCreate(
                request_id=str(uuid4()), description="different", timeout_seconds=300
            ),
            language="en",
        )
    assert caught.value.error_code == ErrorCode.CONFLICT
    background.submit_reserved.assert_not_awaited()


def test_activity_shows_authorized_turn_budget_separately_from_worker_recovery():
    from datetime import timedelta

    from src.infra.assistant.tasks import task_view

    started = utc_now()
    data = record(
        created_at=started - timedelta(days=2),
        timeout_seconds=300,
        authorized_run_started_at=started,
        authorized_run_id="followup",
        followup_count=2,
    )
    view = task_view(
        data,
        child(
            current_run_id="followup",
            task_status="running",
            resume_attempts=3,
            resume_attempts_run_id="followup",
        ),
    )
    assert view["authorized_turns"] == 3
    assert view["recovery_attempts"] == 3
    assert view["deadline_at"] == started + timedelta(seconds=300)
    assert view["started_at"] == started
    older = task_view(
        data, child(current_run_id="followup", resume_attempts=9, resume_attempts_run_id="old")
    )
    assert older["recovery_attempts"] == 0
