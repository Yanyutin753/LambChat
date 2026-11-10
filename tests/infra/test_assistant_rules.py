"""Bounded assistant rules reuse scheduler ticks and detached task admission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.kernel.errors import AppError
from src.kernel.schemas.user import TokenPayload


def rule(mode="observe", **changes):
    return SimpleNamespace(
        id="rule",
        owner_id="owner",
        name="Research updates",
        agent_id="search",
        enabled=True,
        status="active",
        execution_mode="standalone",
        max_retries=0,
        delivery=None,
        input_payload={
            "message": "Check the project",
            "assistant_rule": {
                "assistant_id": "helper",
                "mode": mode,
                "timeout_seconds": 120,
                "max_wakeups": 3,
                **changes,
            },
        },
    )


@pytest.fixture
def runtime(monkeypatch):
    from src.infra.assistant import rules

    collection = SimpleNamespace(
        update_one=AsyncMock(),
        find_one_and_update=AsyncMock(return_value={"assistant_rule_wakeups": 1}),
    )
    storage = SimpleNamespace(
        _get_collection=lambda _: collection,
        create_run=AsyncMock(),
        update_run=AsyncMock(),
        update_task_run_stats=AsyncMock(),
    )
    user = TokenPayload(
        sub="owner",
        username="owner",
        roles=["user"],
        permissions=["chat:write", "scheduled_task:write"],
    )
    monkeypatch.setattr(rules, "_load_user_payload", AsyncMock(return_value=user))
    monkeypatch.setattr(
        rules.AssistantStore,
        "get",
        AsyncMock(return_value=SimpleNamespace(id="helper", status="active")),
    )
    create = AsyncMock(
        return_value={"task_id": "child", "session_id": "child-chat", "status": "queued"}
    )
    monkeypatch.setattr(rules.AssistantTaskService, "create", create)
    return rules, storage, collection, create, user


async def test_observe_records_match_without_submitting_or_calling_a_model(runtime):
    rules, storage, collection, create, _ = runtime
    result = await rules.run_assistant_rule(rule(), "interval", storage)
    assert result["status"] == "observed"
    create.assert_not_awaited()
    saved = storage.create_run.call_args.args[0]
    assert saved.output_result["mode"] == "observe"
    assert saved.output_result["execution_admitted"] is False
    query = collection.find_one_and_update.call_args.args[0]
    assert query["owner_id"] == "owner" and query["enabled"] is True
    assert query["$expr"]["$lt"][1] == 3


async def test_auto_admits_one_bounded_task_with_explicit_rule_authority(runtime):
    rules, storage, _, create, _ = runtime
    result = await rules.run_assistant_rule(rule("auto"), "interval", storage)
    assert result["status"] == "submitted"
    args, kwargs = create.call_args
    assert args[1] == "helper" and args[2].timeout_seconds == 120
    assert isinstance(args[2].request_id, UUID)
    assert kwargs["authorization"]["kind"] == "rule"
    assert kwargs["authorization"]["rule_id"] == "rule"
    assert kwargs["quiet"] is True
    assert storage.update_run.call_args.args[1]["output_result"]["task_id"] == "child"


async def test_exhausted_or_duplicate_claim_never_submits(runtime):
    rules, storage, collection, create, _ = runtime
    collection.find_one_and_update.return_value = None
    assert (await rules.run_assistant_rule(rule("auto"), "interval", storage))["skipped"]
    create.assert_not_awaited()
    storage.create_run.assert_not_awaited()


async def test_off_and_permission_revocation_stop_before_claim(runtime):
    rules, storage, collection, create, user = runtime
    assert (await rules.run_assistant_rule(rule("off"), "interval", storage))["skipped"]
    user.permissions = ["chat:write"]
    with pytest.raises(AppError):
        await rules.run_assistant_rule(rule("auto"), "interval", storage)
    collection.find_one_and_update.assert_not_awaited()
    create.assert_not_awaited()


async def test_event_rule_only_claims_completed_owned_target_and_deduplicates_run(
    runtime, monkeypatch
):
    rules, storage, collection, create, _ = runtime
    get = AsyncMock(return_value={"state": "running", "run_id": "source-run"})
    monkeypatch.setattr(rules.AssistantTaskService, "get", get)
    task = rule("auto", event_task_id="source")
    assert (await rules.run_assistant_rule(task, "interval", storage))["skipped"]
    collection.find_one_and_update.assert_not_awaited()
    get.return_value = {
        "state": "awaiting_review",
        "run_id": "source-run",
        "session_id": "source-chat",
    }
    await rules.run_assistant_rule(task, "interval", storage)
    get.assert_awaited_with(runtime[-1], "helper", "source")
    query = collection.find_one_and_update.call_args.args[0]
    assert query["assistant_rule_last_event"] == {"$ne": "source:source-run"}
    assert create.await_count == 1
    assert "source-chat" in create.call_args.args[2].description


async def test_quiet_result_requires_original_rule_run_and_exact_no_update(monkeypatch):
    from src.infra.assistant import rules
    from src.infra.session import trace_storage
    from src.infra.task.background_task_store import BackgroundTaskStore

    record = {"quiet": True, "authorization": {"kind": "rule"}, "run_id": "run"}
    collection = SimpleNamespace(find_one=AsyncMock(return_value=record))
    monkeypatch.setattr(BackgroundTaskStore, "collection", property(lambda _: collection))
    events = AsyncMock(return_value=[])
    monkeypatch.setattr(
        trace_storage, "get_trace_storage", lambda: SimpleNamespace(get_run_events=events)
    )
    monkeypatch.setattr(
        "src.infra.channel.delivery.extract_delivery_text", lambda *a, **kw: " NO_UPDATE "
    )
    assert await rules.quiet_rule_result("child", "run", "owner", "completed")
    assert not await rules.quiet_rule_result("child", "new-user-run", "owner", "completed")
    assert not await rules.quiet_rule_result("child", "run", "owner", "failed")
    assert collection.find_one.call_args.args[0] == {
        "user_id": "owner",
        "session_id": "child",
        "run_id": "new-user-run",
    }
