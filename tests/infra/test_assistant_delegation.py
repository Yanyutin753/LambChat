"""Chief delegates through the existing queue without adopting a colleague's identity."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.kernel.errors import AppError
from tests.infra.test_assistant_tasks import helper, owner


async def test_delegate_reuses_call_identity_and_preserves_target_configuration(monkeypatch):
    from src.infra.assistant.tasks import AssistantTaskService
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=owner()))
    target = helper()
    monkeypatch.setattr(
        module, "AssistantService", lambda: SimpleNamespace(get=AsyncMock(return_value=target))
    )
    create = AsyncMock(return_value={"status": "queued", "session_id": "child", "task_id": "task"})
    monkeypatch.setattr(AssistantTaskService, "create", create)
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "context": SimpleNamespace(user_id="owner", session_id="chief-chat"),
                "thread_id": "chief-chat",
                "run_id": "run",
            }
        },
        tool_call_id="call",
    )
    first = await module.delegate_assistant_task.coroutine(
        assistant_id="helper", description="Check the launch plan", runtime=runtime
    )
    request = create.call_args.args[2]
    assert request.description == "Check the launch plan"
    assert create.call_args.kwargs["source_session_id"] == "chief-chat"
    assert create.call_args.kwargs["source_run_id"] == "run"
    assert first["assistant_id"] == "helper" and first["status"] == "queued"
    assert first["url"] == "/assistants/helper/chat/child"
    await module.delegate_assistant_task.coroutine(
        assistant_id="helper", description="Check the launch plan", runtime=runtime
    )
    assert create.call_args.args[2].request_id == request.request_id


@pytest.mark.parametrize(
    "changes", [{"kind": "chief"}, {"status": "paused"}, {"status": "archived"}]
)
async def test_delegate_rejects_unavailable_targets_before_admission(monkeypatch, changes):
    from src.infra.assistant.tasks import AssistantTaskService
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=owner()))
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(get=AsyncMock(return_value=helper().model_copy(update=changes))),
    )
    create = AsyncMock()
    monkeypatch.setattr(AssistantTaskService, "create", create)
    with pytest.raises(AppError):
        await module.delegate_assistant_task.coroutine(
            assistant_id="helper",
            description="Check a plan",
            runtime=SimpleNamespace(config={"configurable": {}}, tool_call_id="call"),
        )
    create.assert_not_awaited()


async def test_delegated_task_keeps_source_delivery_and_target_memory_separate(monkeypatch):
    from uuid import uuid4

    from src.api.routes import chat_request_config
    from src.infra.assistant.store import AssistantStore
    from src.infra.assistant.tasks import AssistantTaskService, task_view
    from src.kernel.schemas.assistant import AssistantTaskCreate
    from tests.infra.test_assistant_tasks import child

    chief = helper().model_copy(update={"id": "chief", "kind": "chief", "session_id": "chief-chat"})
    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=chief))
    monkeypatch.setattr(chat_request_config, "resolve_persona_request", AsyncMock())
    records = {}

    async def reserve(value):
        return records.setdefault(value["_id"], value)

    background = SimpleNamespace(
        store=SimpleNamespace(reserve=reserve),
        submit_reserved=AsyncMock(return_value={"status": "queued"}),
    )
    service = AssistantTaskService(
        assistants=SimpleNamespace(
            get=AsyncMock(return_value=helper()), validate_configuration=AsyncMock()
        ),
        background=background,
    )
    data = AssistantTaskCreate(request_id=uuid4(), description="Check a plan")
    await service.create(
        owner(), "helper", data, source_session_id="chief-chat", source_run_id="chief-run"
    )
    saved = next(iter(records.values()))
    assert saved["parent_session_id"] == "chief-chat"
    assert saved["parent_run_id"] == "chief-run"
    assert saved["assistant_source_session_id"] == "coordinator"
    assert saved["assistant_id"] == "helper"
    assert saved["authorization"]["source_assistant_id"] == "chief"
    assert saved["authorization"]["kind"] == "conversation"
    view = task_view(saved, child(background_task_id=saved["_id"]))
    assert view["source_session_id"] == "chief-chat"
    assert view["source_assistant_id"] == "chief"
    assert view["assistant_id"] == "helper"
    service.assistants.get.return_value = helper().model_copy(
        update={"id": "different", "session_id": "other"}
    )
    with pytest.raises(AppError):
        await service.create(
            owner(), "different", data, source_session_id="chief-chat", source_run_id="chief-run"
        )
    assert len(records) == 1


@pytest.mark.parametrize(
    "source", [None, helper(), helper().model_copy(update={"kind": "chief", "status": "paused"})]
)
async def test_delegation_source_must_still_be_an_owned_active_chief(monkeypatch, source):
    from uuid import uuid4

    from src.infra.assistant.store import AssistantStore
    from src.infra.assistant.tasks import AssistantTaskService
    from src.kernel.schemas.assistant import AssistantTaskCreate

    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=source))
    reserve = AsyncMock()
    service = AssistantTaskService(
        assistants=SimpleNamespace(
            get=AsyncMock(return_value=helper()), validate_configuration=AsyncMock()
        ),
        background=SimpleNamespace(store=SimpleNamespace(reserve=reserve)),
    )
    with pytest.raises(AppError):
        await service.create(
            owner(),
            "helper",
            AssistantTaskCreate(request_id=uuid4(), description="Check a plan"),
            source_session_id="chief-chat",
            source_run_id="run",
        )
    reserve.assert_not_awaited()


@pytest.mark.parametrize(
    "target_status,chief_status",
    [("paused", "active"), ("archived", "active"), ("active", "paused")],
)
async def test_queued_delegation_rechecks_both_participants_before_model_execution(
    monkeypatch, target_status, chief_status
):
    from src.infra.assistant.store import AssistantStore
    from src.infra.task import background_admission, background_tasks
    from tests.infra.test_assistant_tasks import record

    saved = record(
        assistant_id="helper",
        assistant_source_session_id="coordinator",
        authorization={"kind": "conversation", "source_assistant_id": "chief"},
        parent_session_id="chief-chat",
    )
    monkeypatch.setattr(
        background_admission, "validate_background_run_admission", AsyncMock(return_value=saved)
    )
    monkeypatch.setattr(
        AssistantStore,
        "get",
        AsyncMock(return_value=helper().model_copy(update={"status": target_status})),
    )
    monkeypatch.setattr(
        AssistantStore,
        "for_session",
        AsyncMock(
            return_value=helper().model_copy(
                update={
                    "id": "chief",
                    "kind": "chief",
                    "status": chief_status,
                    "session_id": "chief-chat",
                }
            )
        ),
    )
    execute = AsyncMock(side_effect=AssertionError("execution reached without revalidation"))
    monkeypatch.setattr(background_tasks, "validate_background_execution", execute)
    with pytest.raises(AppError):
        async for _ in background_tasks.execute_background_stream(
            "child", "search", "check", "owner", presenter=SimpleNamespace(run_id="run")
        ):
            pass
    execute.assert_not_awaited()


async def test_delegated_work_uses_target_memory_not_chief_history(monkeypatch):
    from src.infra.assistant.memory import session_assistant_partition
    from src.infra.assistant.store import AssistantStore
    from src.infra.task.background_task_store import BackgroundTaskStore
    from tests.infra.test_assistant_tasks import record

    saved = record(
        assistant_id="helper",
        assistant_source_session_id="coordinator",
        parent_session_id="chief-chat",
    )
    collection = SimpleNamespace(find_one=AsyncMock(return_value=saved))
    monkeypatch.setattr(BackgroundTaskStore, "collection", property(lambda self: collection))
    monkeypatch.setattr(AssistantStore, "get", AsyncMock(return_value=helper()))
    assert (
        await session_assistant_partition("child", "owner", {"background_task_id": "task"})
        == "assistant-memory:helper"
    )
    collection.find_one.assert_awaited_once_with(
        {"_id": "task", "user_id": "owner", "session_id": "child"}
    )


async def test_legacy_manual_work_still_validates_without_delegation_metadata(monkeypatch):
    from src.infra.assistant.store import AssistantStore
    from src.infra.assistant.tasks import validate_task_assistant
    from tests.infra.test_assistant_tasks import record

    monkeypatch.setattr(AssistantStore, "get", AsyncMock(return_value=helper()))
    lookup = AsyncMock()
    monkeypatch.setattr(AssistantStore, "for_session", lookup)
    await validate_task_assistant(record(assistant_id="helper"), "owner")
    lookup.assert_not_awaited()


def test_group_members_cannot_discover_chief_delegation_tool():
    from src.agents.team_agent.role_tools import build_role_tool_scope
    from src.infra.tool.assistant_tool import delegate_assistant_task
    from src.infra.tool.deferred_manager import DeferredToolManager

    direct, deferred = build_role_tool_scope(
        [delegate_assistant_task],
        DeferredToolManager(
            all_deferred_tools=[],
            deferred_system_tools=[delegate_assistant_task],
            session_id="group",
        ),
        mcp_servers=[],
        scope="member",
    )
    assert direct == []
    assert deferred.get_deferred_stubs() == []
