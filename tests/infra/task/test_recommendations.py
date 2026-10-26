from contextvars import ContextVar
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.runnables.config import ensure_config

from src.infra.utils.datetime import utc_now


@pytest.fixture
def dependencies(monkeypatch):
    from src.infra.task import recommendations

    record = {
        "user_id": "owner",
        "session_id": "session",
        "run_id": "run",
        "trace_id": "trace",
        "recommendation_lease": "lease",
        "recommendation_due_at": utc_now() + timedelta(seconds=120),
        "recommendation_request": {
            "user_input": "question",
            "output_text": "answer",
            "history_context": "history",
            "response_language": "zh",
        },
    }
    collection = SimpleNamespace(
        find_one_and_update=AsyncMock(side_effect=[record, None]),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
    )
    storage = SimpleNamespace(collection=collection, ensure_indexes_if_needed=AsyncMock())
    websocket = SimpleNamespace(send_to_user_with_broadcast=AsyncMock())
    generate = AsyncMock(return_value=["a?", "b?", "c?"])
    monkeypatch.setattr(recommendations, "get_trace_storage", lambda: storage)
    monkeypatch.setattr(recommendations, "get_connection_manager", lambda: websocket)
    monkeypatch.setattr(recommendations, "generate_recommend_questions", generate)
    return recommendations, collection, websocket, generate, record


async def test_recommendation_job_does_not_inherit_chat_context(dependencies):
    module, collection, websocket, generate, record = dependencies
    parent = ContextVar("private_parent", default=None)
    token = parent.set("must not inherit")

    async def model(**kwargs):
        assert parent.get() is None
        config = ensure_config()
        assert config["configurable"] == {
            key: record[key] for key in ("user_id", "session_id", "run_id", "trace_id")
        }
        assert not config.get("callbacks")
        assert kwargs == record["recommendation_request"]
        return ["a?", "b?", "c?"]

    generate.side_effect = model
    try:
        await module.scan_recommendations({})
    finally:
        parent.reset(token)
    message = websocket.send_to_user_with_broadcast.await_args.args
    assert message == (
        "owner",
        {
            "type": "recommend:questions",
            "data": {"session_id": "session", "run_id": "run", "questions": ["a?", "b?", "c?"]},
        },
    )
    writes = collection.update_one.await_args_list
    assert all(call.args[0]["recommendation_lease"] == "lease" for call in writes)
    assert "recommendation_request" in writes[-1].args[1]["$unset"]
    assert all("status" not in call.args[1].get("$set", {}) for call in writes)


async def test_restart_reuses_saved_questions_and_keeps_pending_on_push_failure(dependencies):
    module, collection, websocket, generate, record = dependencies
    record["recommend_questions"] = ["saved?", "b?", "c?"]
    websocket.send_to_user_with_broadcast.side_effect = RuntimeError("deploy")
    await module.scan_recommendations({})
    generate.assert_not_awaited()
    final_update = collection.update_one.await_args.args[1]
    assert "recommendation_request" not in final_update.get("$unset", {})
    assert "recommendation_due_at" in final_update["$set"]


async def test_stale_lease_cannot_publish_or_delete_pending_request(dependencies):
    module, collection, websocket, _, _ = dependencies
    collection.update_one.return_value.modified_count = 0
    await module.scan_recommendations({})
    websocket.send_to_user_with_broadcast.assert_not_awaited()
    assert all(
        "recommendation_request" not in call.args[1].get("$unset", {})
        for call in collection.update_one.await_args_list
    )


async def test_enqueue_persists_before_return_and_does_not_reset_existing_request(dependencies):
    module, collection, _, _, _ = dependencies
    presenter = SimpleNamespace(
        config=SimpleNamespace(user_id="owner", session_id="session"),
        run_id="run",
        trace_id="trace",
    )
    await module.enqueue_recommendation(presenter, "question", "answer", "history", "zh")
    query, update = collection.update_one.await_args.args
    assert query == {
        "user_id": "owner",
        "session_id": "session",
        "run_id": "run",
        "trace_id": "trace",
        "recommendation_request": {"$exists": False},
        "recommend_questions.0": {"$exists": False},
    }
    assert update["$set"]["recommendation_request"] == {
        "user_input": "question",
        "output_text": "answer",
        "history_context": "history",
        "response_language": "zh",
    }
    assert "recommendation_due_at" in update["$set"]
    assert collection.update_one.await_args.kwargs.get("upsert") is not True


async def test_claim_uses_expiring_lease_for_cross_instance_recovery(dependencies):
    module, collection, _, _, _ = dependencies
    await module.scan_recommendations({})
    query, update = collection.find_one_and_update.await_args_list[0].args
    assert query["recommendation_request"] == {"$exists": True}
    assert "$lte" in query["recommendation_due_at"]
    assert update["$set"]["recommendation_due_at"] > query["recommendation_due_at"]["$lte"]
    assert update["$set"]["recommendation_lease"]


async def test_shutdown_releases_recommendation_for_next_instance(dependencies):
    import asyncio

    module, collection, websocket, generate, _ = dependencies
    started = asyncio.Event()

    async def pending(**kwargs):
        started.set()
        await asyncio.Event().wait()

    generate.side_effect = pending
    scan = asyncio.create_task(module.scan_recommendations({}))
    await started.wait()
    scan.cancel()
    with pytest.raises(asyncio.CancelledError):
        await scan
    websocket.send_to_user_with_broadcast.assert_not_awaited()
    update = collection.update_one.await_args.args[1]
    assert "recommendation_request" not in update.get("$unset", {})
    assert update["$set"]["recommendation_due_at"] <= utc_now()


async def test_overlapping_scan_does_not_exceed_process_limit(dependencies):
    import asyncio

    module, collection, _, generate, _ = dependencies
    started, release = asyncio.Event(), asyncio.Event()

    async def model(**kwargs):
        started.set()
        await release.wait()
        return ["a?", "b?", "c?"]

    generate.side_effect = model
    first = asyncio.create_task(module.scan_recommendations({}))
    await started.wait()
    before = collection.find_one_and_update.await_count
    try:
        await module.scan_recommendations({})
        assert collection.find_one_and_update.await_count == before
    finally:
        release.set()
        await first
