"""Detached work must retain normal admission and avoid replaying uncertain writes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class Store:
    def __init__(self):
        self.records = {}

    async def reserve(self, record):
        return self.records.setdefault(record["_id"], record.copy())

    async def claim(self, task_id):
        item = self.records[task_id]
        if item["state"] != "reserved":
            return None
        item["state"] = "submitting"
        item["lease_token"] = "token"
        return item.copy()

    async def mark_attention_delivered(self, task_id):
        self.records[task_id]["attention_pending"] = False

    async def finish(self, task_id, token, state, **fields):
        item = self.records[task_id]
        if item.get("lease_token") != token:
            return False
        item.update(state=state, **fields)
        return True


def service(*, permission=True, depth=0, submit=None):
    from src.infra.task.background_tasks import BackgroundTaskService

    parent = SimpleNamespace(
        user_id="u",
        metadata={
            "current_run_id": "parent-run",
            "agent_id": "fast",
            "background_depth": depth,
            "agent_options": {"model_id": "model", "_resolved_model_config": {"secret": "private"}},
            "disabled_tools": ["eval"],
            "persistent_goal_id": "must-not-inherit",
        },
    )
    sessions = SimpleNamespace(
        get_session=AsyncMock(
            side_effect=lambda session_id: parent if session_id == "parent" else None
        ),
        storage=SimpleNamespace(create=AsyncMock()),
    )
    user = SimpleNamespace(
        sub="u", permissions=["chat:write"] if permission else [], roles=["fresh"]
    )
    submit = submit or AsyncMock(return_value={"status": "pending", "run_id": "unused"})
    return (
        BackgroundTaskService(
            store=Store(),
            sessions=sessions,
            load_user=AsyncMock(return_value=user),
            submit=submit,
            publish_attention=AsyncMock(),
        ),
        submit,
        sessions,
    )


async def start(svc, **extra):
    return await svc.start(
        user_id="u",
        parent_session_id="parent",
        parent_run_id="parent-run",
        call_id="call",
        description="Compute 2+2",
        **extra,
    )


async def test_repeated_source_tool_call_submits_one_independent_session():
    svc, submit, sessions = service()
    first = await start(svc)
    second = await start(svc)
    assert first["session_id"] != "parent"
    assert first["run_id"] != "parent-run"
    assert second["task_id"] == first["task_id"]
    assert submit.await_count == sessions.storage.create.await_count == 1


async def test_parent_goal_dispatch_is_isolated_and_reserved_run_is_internal():
    from src.infra.goal_continuation import GOAL_DISPATCH
    from src.infra.goal_runtime import SUBMISSION_GOAL
    from src.infra.task.background_tasks import BACKGROUND_SUBMISSION_RUN

    async def submit(request, http_request, agent_id, user):
        assert GOAL_DISPATCH.get() is None
        assert SUBMISSION_GOAL.get() is None
        assert BACKGROUND_SUBMISSION_RUN.get()
        assert request.goal is None
        assert request.disabled_tools == ["eval"]
        assert request.agent_options == {"model_id": "model"}
        assert user.roles == ["fresh"]
        return {"status": "queued"}

    svc, _, _ = service(submit=submit)
    token = GOAL_DISPATCH.set(SimpleNamespace(id="parent-goal"))
    goal_token = SUBMISSION_GOAL.set(("parent", "u", 1, "parent-run"))
    try:
        result = await start(svc)
        assert result["status"] == "queued"
        assert GOAL_DISPATCH.get().id == "parent-goal"
        assert SUBMISSION_GOAL.get() == ("parent", "u", 1, "parent-run")
    finally:
        GOAL_DISPATCH.reset(token)
        SUBMISSION_GOAL.reset(goal_token)


async def test_current_chat_permission_is_checked_before_writes():
    svc, submit, sessions = service(permission=False)
    with pytest.raises(Exception):
        await start(svc)
    submit.assert_not_awaited()
    sessions.storage.create.assert_not_awaited()
    assert svc.store.records == {}


async def test_detached_child_cannot_recursively_fan_out():
    svc, submit, sessions = service(depth=1)
    with pytest.raises(ValueError, match="depth"):
        await start(svc)
    submit.assert_not_awaited()
    sessions.storage.create.assert_not_awaited()


async def test_uncertain_submission_is_not_replayed():
    svc, submit, _ = service(submit=AsyncMock(side_effect=RuntimeError("write uncertain")))
    first = await start(svc)
    second = await start(svc)
    assert first["status"] == second["status"] == "error"
    assert first["error_code"] == "background_task_uncertain"
    assert submit.await_count == 1


async def test_child_metadata_links_parent_without_goal_or_credentials():
    svc, _, sessions = service()
    result = await start(svc)
    metadata = sessions.storage.create.await_args.args[0].metadata
    assert metadata["background_task_id"] == result["task_id"]
    assert metadata["background_parent_session_id"] == "parent"
    assert metadata["background_parent_run_id"] == "parent-run"
    assert metadata["background_depth"] == 1
    assert "persistent_goal_id" not in metadata
    assert "private" not in str(metadata)


async def test_recovery_adopts_persisted_run_without_submitting_again():
    svc, submit, sessions = service()
    result = await start(svc)
    record = svc.store.records[result["task_id"]]
    record["state"] = "submitting"
    record["execution_mode"] = "local"
    sessions.get_session.side_effect = None
    sessions.get_session.return_value = SimpleNamespace(
        user_id="u", metadata={"current_run_id": result["run_id"]}
    )
    await svc.recover(record)
    assert record["state"] == "submitted"
    assert submit.await_count == 1


async def test_expired_uncertain_intent_is_paused_without_replay():
    svc, submit, sessions = service()
    result = await start(svc)
    record = svc.store.records[result["task_id"]]
    record["state"] = "submitting"
    record["execution_mode"] = "local"
    sessions.get_session.side_effect = None
    sessions.get_session.return_value = None
    await svc.recover(record)
    assert record["state"] == "uncertain"
    assert submit.await_count == 1


async def test_persona_resolution_cannot_expand_parent_whitelists():
    from src.infra.task.background_tasks import apply_background_restrictions
    from src.kernel.schemas.agent import AgentRequest

    request = AgentRequest(
        message="work",
        disabled_tools=["ask_human"],
        enabled_skills=["allowed", "new"],
        enabled_mcp_servers=["known", "new"],
    )
    apply_background_restrictions(
        request,
        {
            "disabled_tools": ["eval"],
            "enabled_skills": ["allowed"],
            "enabled_mcp_servers": ["known"],
        },
    )
    assert request.disabled_tools == ["ask_human", "eval"]
    assert request.enabled_skills == ["allowed"]
    assert request.enabled_mcp_servers == ["known"]


def test_fresh_worker_can_resolve_detached_executor_after_restart():
    from src.infra.task.arq_worker import _resolve_executor
    from src.infra.task.background_tasks import execute_background_stream

    assert _resolve_executor("background_agent_stream") is execute_background_stream


async def test_parent_disabling_detached_tool_blocks_admission():
    svc, submit, sessions = service()
    parent = await sessions.get_session("parent")
    parent.metadata["disabled_tools"].append("start_background_task")
    with pytest.raises(Exception):
        await start(svc)
    submit.assert_not_awaited()
    sessions.storage.create.assert_not_awaited()


async def test_worker_rechecks_revoked_chat_permission_before_execution(monkeypatch):
    from src.api import deps
    from src.infra.session.manager import SessionManager
    from src.infra.task.background_tasks import validate_background_execution

    monkeypatch.setattr(
        SessionManager,
        "get_session",
        AsyncMock(
            return_value=SimpleNamespace(user_id="u", metadata={"background_task_id": "task"})
        ),
    )
    monkeypatch.setattr(
        deps,
        "_load_user_payload",
        AsyncMock(return_value=SimpleNamespace(sub="u", permissions=[], roles=["revoked"])),
    )
    with pytest.raises(Exception):
        await validate_background_execution("child", "fast", "u", {"model_id": "model"})


async def test_worker_revalidates_current_persona_and_model_and_intersects_limits(monkeypatch):
    from src.api import deps
    from src.api.routes import chat, chat_request_config
    from src.infra.session.manager import SessionManager
    from src.infra.task.background_tasks import validate_background_execution

    metadata = {
        "persona_preset_id": "preset",
        "enabled_skills": ["old"],
        "background_restrictions": {"enabled_skills": ["old"], "disabled_tools": ["eval"]},
    }
    monkeypatch.setattr(
        SessionManager,
        "get_session",
        AsyncMock(return_value=SimpleNamespace(user_id="u", metadata=metadata)),
    )
    monkeypatch.setattr(
        deps,
        "_load_user_payload",
        AsyncMock(
            return_value=SimpleNamespace(
                sub="u", permissions=["chat:write"], roles=["current-role"]
            )
        ),
    )

    async def persona(request, user):
        assert request.persona_preset_id == "preset"
        assert user.roles == ["current-role"]
        request.enabled_skills = ["old", "newly-added"]
        request.persona_system_prompt = "current-authorized-prompt"

    model = AsyncMock()
    monkeypatch.setattr(chat_request_config, "resolve_persona_request", persona)
    monkeypatch.setattr(chat, "validate_agent_model_access", model)
    request = await validate_background_execution(
        "child", "fast", "u", {"model_id": "model", "_resolved_model_config": {"key": "secret"}}
    )
    model.assert_awaited_once()
    assert model.await_args.args[1].roles == ["current-role"]
    assert request.enabled_skills == ["old"]
    assert request.disabled_tools == ["eval"]
    assert request.persona_system_prompt == "current-authorized-prompt"
    assert "_resolved_model_config" not in request.agent_options


async def test_recovery_never_requeues_running_or_approval_suspended_work(monkeypatch):
    from src.infra.task import manager
    from src.infra.task.arq_payloads import TaskArqPayloadStore

    svc, _, sessions = service()
    result = await start(svc)
    record = svc.store.records[result["task_id"]]
    record.update(state="submitting", execution_mode="arq")
    sessions.get_session.side_effect = None
    sessions.get_session.return_value = SimpleNamespace(
        user_id="u", metadata={"current_run_id": result["run_id"], "task_status": "waiting_human"}
    )
    load = AsyncMock(return_value={"session_id": result["session_id"]})
    enqueue = AsyncMock()
    monkeypatch.setattr(TaskArqPayloadStore, "load", load)
    monkeypatch.setattr(
        manager,
        "get_task_manager",
        lambda: SimpleNamespace(
            _get_arq_pool=AsyncMock(return_value=SimpleNamespace(enqueue_job=enqueue))
        ),
    )
    await svc.recover(record)
    enqueue.assert_not_awaited()
    assert record["state"] == "submitted"


@pytest.mark.parametrize("field", ["enabled_skills", "enabled_mcp_servers"])
def test_disjoint_background_whitelist_fails_closed(field):
    from src.infra.task.background_tasks import apply_background_restrictions
    from src.kernel.schemas.agent import AgentRequest

    request = AgentRequest(message="work", **{field: ["newly-added"]})
    with pytest.raises(Exception):
        apply_background_restrictions(request, {field: ["parent-only"]})


async def test_reserved_dispatch_auth_failure_creates_visible_failed_child_and_notice():
    svc, submit, sessions = service()
    svc.load_user.side_effect = [
        SimpleNamespace(sub="u", permissions=["chat:write"], roles=[]),
        RuntimeError("permission revoked"),
    ]
    svc.publish_attention = AsyncMock()
    result = await start(svc)
    assert result["status"] == "error"
    sessions.storage.create.assert_awaited_once()
    svc.publish_attention.assert_awaited_once()
    submit.assert_not_awaited()


async def test_attention_duplicate_journal_does_not_repeat_live_notification(monkeypatch):
    from src.infra import websocket
    from src.infra.task import background_attention
    from src.infra.task.background_attention import publish_background_attention

    record = {
        "_id": "task",
        "user_id": "u",
        "session_id": "child",
        "run_id": "run",
        "parent_session_id": "parent",
    }
    sessions = SimpleNamespace(
        get_session=AsyncMock(
            return_value=SimpleNamespace(user_id="u", metadata={"background_task_id": "task"})
        ),
        update_session_metadata=AsyncMock(),
    )
    journal = SimpleNamespace(record_once=AsyncMock(return_value=({"id": "same"}, False)))
    send = AsyncMock()
    monkeypatch.setattr(background_attention, "TaskCompletionStore", lambda: journal)
    monkeypatch.setattr(
        websocket,
        "get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=send),
    )
    await publish_background_attention(record, "failed", sessions)
    journal.record_once.assert_awaited_once()
    send.assert_not_awaited()


async def test_uncertain_admission_does_not_overwrite_running_child_status(monkeypatch):
    from src.infra import websocket
    from src.infra.task import background_attention
    from src.infra.task.background_attention import publish_background_attention

    record = {
        "_id": "task",
        "user_id": "u",
        "session_id": "child",
        "run_id": "run",
        "parent_session_id": "parent",
    }
    sessions = SimpleNamespace(
        get_session=AsyncMock(
            return_value=SimpleNamespace(
                user_id="u",
                metadata={
                    "background_task_id": "task",
                    "current_run_id": "run",
                    "task_status": "running",
                },
            )
        ),
        update_session_metadata=AsyncMock(),
    )
    journal = SimpleNamespace(record_once=AsyncMock(return_value=({"id": "notice"}, True)))
    monkeypatch.setattr(background_attention, "TaskCompletionStore", lambda: journal)
    monkeypatch.setattr(
        websocket,
        "get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=AsyncMock(return_value=1)),
    )
    await publish_background_attention(record, "uncertain", sessions)
    assert "task_status" not in sessions.update_session_metadata.await_args.args[1]
    assert journal.record_once.await_args.args[1]["status"] == "waiting_human"
