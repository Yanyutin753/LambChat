"""Real Mongo atomicity tests, using a disposable database, never account collections."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.infra.usage.quota import UsageQuota, quota_windows
from src.kernel.errors import AppError, ErrorCode


@pytest.fixture
async def quota_db(monkeypatch):
    if os.environ.get("LAMBCHAT_QUOTA_INTEGRATION") != "1":
        pytest.skip("Set LAMBCHAT_QUOTA_INTEGRATION=1 to verify real Mongo atomicity")
    from pymongo import AsyncMongoClient

    from src.infra.storage.mongodb import build_mongo_connection_string

    client = AsyncMongoClient(
        build_mongo_connection_string(), serverSelectionTimeoutMS=3000, tz_aware=True
    )
    db = client[f"test_lambchat_quota_{uuid.uuid4().hex}"]
    from src.infra.usage import auxiliary
    from src.infra.usage.storage import UsageStorage

    usage_storage = UsageStorage()
    usage_storage._collection = db["usage_logs"]
    monkeypatch.setattr(auxiliary, "get_usage_storage", lambda: usage_storage)
    try:
        await client.admin.command("ping")
        yield UsageQuota(db["quotas"])
    finally:
        await client.drop_database(db.name)
        await client.close()


async def test_concurrent_calls_check_settled_usage_then_stop_after_limit(quota_db):
    async def attempt():
        try:
            return await quota_db.reserve("user", (1, 10), 0.3)
        except AppError as error:
            assert error.error_code is ErrorCode.USAGE_QUOTA_EXCEEDED
            return None

    results = await asyncio.gather(*(attempt() for _ in range(8)))
    accepted = [result for result in results if result]
    assert len(accepted) == 8
    snapshot = await quota_db.snapshot("user", (1, 10))
    assert snapshot["five_hour"]["remaining_usd"] == 1
    assert not snapshot["five_hour"]["blocked"]
    await asyncio.gather(*(quota_db.settle(result, 0.2) for result in accepted))
    # Replaying settlement is harmless, even across concurrent writers.
    await asyncio.gather(*(quota_db.settle(accepted[0], 0.9) for _ in range(3)))
    snapshot = await quota_db.snapshot("user", (1, 10))
    assert snapshot["five_hour"]["used_usd"] == 1.6
    assert snapshot["five_hour"]["reserved_usd"] == 0
    assert snapshot["weekly"]["used_usd"] == 1.6
    with pytest.raises(AppError) as denied:
        await quota_db.reserve("user", (1, 10), 0)
    assert denied.value.args_data["reason"] == "exhausted"


async def test_settlement_notifies_only_after_durable_change_including_late_usage(
    quota_db, monkeypatch
):
    snapshots = []

    async def notify(user_id):
        snapshot = await quota_db.snapshot(user_id, (1, 10))
        snapshots.append((snapshot["five_hour"]["used_usd"], snapshot["five_hour"]["unknown"]))

    monkeypatch.setattr("src.infra.usage.notifications.broadcast_quota_changed", notify)
    call = await quota_db.reserve("user", (1, 10), 0)
    await quota_db.settle(call, None)
    await quota_db.settle(call, None)
    await quota_db.settle(call, 0.2)
    await quota_db.settle(call, 0.2)
    assert snapshots == [(0, True), (0.2, False)]


async def test_running_usage_updates_one_row_without_becoming_a_failure(quota_db):
    from src.infra.usage.storage import UsageStorage

    storage = UsageStorage()
    storage._collection = quota_db.collection.database["usage_logs"]
    await storage.ensure_indexes()
    trace = dict(trace_id="active", user_id="user", status="running", started_at=datetime.now(UTC))
    for revision, tokens in [(1, 100), (2, 200)]:
        await storage.upsert_usage_log_from_trace_metadata(
            {**trace, "event_revision": revision},
            dict(
                input_tokens=tokens,
                output_tokens=10,
                total_tokens=tokens + 10,
                cache_read_tokens=0,
                cache_creation_tokens=0,
                input_includes_cache=True,
                usage_incomplete=False,
            ),
        )
    assert await storage.collection.count_documents({}) == 1
    dashboard = await storage.get_usage_dashboard()
    assert dashboard["summary"]["total_tokens"] == 210
    assert dashboard["summary"]["failed_requests"] == 0
    assert dashboard["daily"][0]["failed_requests"] == 0


async def test_model_end_persists_and_notifies_while_trace_is_still_running(quota_db, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.infra.agent.events.processor import AgentEventProcessor
    from src.infra.session.dual_writer import DualEventWriter
    from src.infra.session.storage import SessionStorage
    from src.infra.session.trace_storage import TraceStorage
    from src.infra.usage.storage import UsageStorage
    from src.infra.writer.present import create_presenter
    from src.kernel.config import settings

    db = quota_db.collection.database
    sessions = SessionStorage()
    sessions._collection = db[settings.MONGODB_SESSIONS_COLLECTION]
    trace = TraceStorage()
    trace._collection = db[settings.MONGODB_TRACES_COLLECTION]
    trace._chunks_collection = db[settings.MONGODB_TRACE_EVENT_CHUNKS_COLLECTION]
    trace._session_storage = sessions
    usage = UsageStorage()
    usage._collection = db["usage_logs"]
    writer = DualEventWriter()
    writer._trace = trace
    notifications = []

    async def notify(user_id, event):
        assert user_id == "user"
        saved = await usage.collection.find_one({"trace_id": "trace"})
        notifications.append((saved["input_tokens"], saved["status"]))

    monkeypatch.setattr("src.infra.session.storage.SessionStorage", lambda: sessions)
    monkeypatch.setattr("src.infra.session.dual_writer.get_dual_writer", lambda: writer)
    monkeypatch.setattr("src.infra.session.trace_usage_log.get_trace_storage", lambda: trace)
    monkeypatch.setattr("src.infra.usage.storage.get_usage_storage", lambda: usage)
    monkeypatch.setattr(
        "src.infra.session.trace_usage_log.get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=notify),
    )
    monkeypatch.setattr(
        "src.infra.agent.events.processor.compute_usage_cost", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        "src.infra.session.conversation_history.schedule_conversation_trace_index",
        lambda *args: None,
    )
    # Redis delivery is independent; the Mongo buffering, chunks and projection stay real.
    monkeypatch.setattr(writer, "_write_to_redis_direct", AsyncMock(return_value=True))
    await sessions.collection.insert_one({"session_id": "session", "user_id": "user"})
    assert await trace.create_trace("trace", "session", user_id="user")
    await usage.ensure_indexes()
    presenter = create_presenter(session_id="session", trace_id="trace", agent_id="search")
    presenter._trace_created = True
    processor = AgentEventProcessor(presenter)
    for run in ["one", "two"]:
        await processor.process_event(
            {
                "event": "on_chat_model_end",
                "run_id": run,
                "metadata": {},
                "data": {
                    "output": SimpleNamespace(
                        usage_metadata={
                            "input_tokens": 100,
                            "output_tokens": 10,
                            "total_tokens": 110,
                            "input_token_details": {"cache_read": 0, "cache_creation": 0},
                        },
                        response_metadata={},
                    )
                },
            }
        )
    assert notifications == [(100, "running"), (200, "running")]
    assert await trace.complete_trace("trace")
    assert notifications[-1] == (200, "completed")
    assert await usage.collection.count_documents({}) == 1


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("priced", [False, True])
async def test_each_model_call_checks_real_ledger_without_output_cap(
    quota_db, monkeypatch, streaming, priced
):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from langchain_core.messages import AIMessageChunk, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

    from src.infra.llm import quota
    from src.infra.pricing.calculator import PriceRates

    rates = PriceRates(input=1_000_000, output=1_000_000, cache_write_included=True)
    monkeypatch.setattr(quota, "UsageQuota", lambda: quota_db)
    monkeypatch.setattr(quota, "quota_user_id", lambda: "user")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(1, 5)))
    monkeypatch.setattr(
        "src.infra.pricing.service.resolve_price",
        AsyncMock(return_value=SimpleNamespace(rates=rates) if priced else None),
    )

    class Provider:
        calls = 0

        async def _astream(self, *args, **kwargs):
            self.calls += 1
            quota._record_raw_usage(
                {"prompt_tokens": 1, "completion_tokens": 1},
                ("prompt_tokens", "completion_tokens"),
            )
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="ok",
                    usage_metadata={
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "total_tokens": 2,
                        "input_token_details": {"cache_read": 0},
                    },
                )
            )

        async def _agenerate(self, *args, **kwargs):
            chunks = [chunk async for chunk in self._astream(*args, **kwargs)]
            return ChatResult(generations=[ChatGeneration(message=chunks[0].message)])

    class Model(quota.QuotaChatMixin, Provider):
        quota_provider = None
        quota_model_config_id = None

    model = Model()

    async def invoke():
        messages = [HumanMessage(content="hello")]
        if streaming:
            return [chunk async for chunk in model._astream(messages)]
        return await model._agenerate(messages)

    await invoke()
    snapshot = await quota_db.snapshot("user", (1, 5))
    assert snapshot["five_hour"]["used_usd"] == (2 if priced else 0)
    assert snapshot["five_hour"]["unknown"] is (not priced)
    if priced:
        with pytest.raises(AppError) as denied:
            await invoke()
        assert denied.value.error_code is ErrorCode.USAGE_QUOTA_EXCEEDED
        assert model.calls == 1
    else:
        await invoke()
        assert model.calls == 2


async def test_weekly_exhaustion_zero_and_users_are_independent(quota_db):
    call = await quota_db.reserve("user", (10, 0.3), 0.3)
    await quota_db.settle(call, 0.3)
    with pytest.raises(AppError):
        await quota_db.reserve("user", (10, 0.3), 0)
    with pytest.raises(AppError):
        await quota_db.reserve("zero", (0, None), 0)
    other = await quota_db.reserve("other", (1, 1), 0.1)
    await quota_db.settle(other, 0)
    assert (await quota_db.snapshot("other", (1, 1)))["five_hour"]["used_usd"] == 0


async def test_unknown_usage_remains_visible_without_blocking_capped_windows(quota_db):
    call = await quota_db.reserve("user", (1, 5), 0.1)
    await quota_db.settle(call, None)
    await quota_db.settle(call, None)
    snapshot = await quota_db.snapshot("user", (1, 5))
    assert snapshot["five_hour"]["reserved_usd"] == 0.1
    assert snapshot["five_hour"]["unknown"] and not snapshot["five_hour"]["blocked"]
    allowed = await quota_db.reserve("user", (1, 5), 0.1)
    await quota_db.settle(allowed, 0)
    unlimited = await quota_db.reserve("user", (None, None), 0.1)
    await quota_db.settle(unlimited, 0.01)
    await quota_db.settle(call, 0.02)
    snapshot = await quota_db.snapshot("user", (1, 5))
    assert not snapshot["five_hour"]["unknown"]
    assert snapshot["five_hour"]["reserved_usd"] == 0
    assert snapshot["five_hour"]["used_usd"] == 0.03


async def test_late_settlement_charges_original_windows_and_survives_restart(quota_db):
    old_windows = quota_windows(datetime(2026, 1, 4, 15, tzinfo=UTC))
    call = await quota_db.reserve("user", (1, 5), 0.5, windows=old_windows)
    restarted = UsageQuota(quota_db.collection)
    await restarted.settle(call, 0.25)
    doc = await quota_db.collection.find_one({"_id": "user"})
    assert doc["periods"][old_windows[0][0]]["used"] == 250_000_000
    assert (await restarted.snapshot("user", (1, 5)))["five_hour"]["used_usd"] == 0


async def test_unlimited_usage_is_recorded_before_a_budget_is_enabled(quota_db):
    call = await quota_db.reserve("user", (None, None), 1)
    await quota_db.settle(call, 0.75)
    with pytest.raises(AppError):
        await quota_db.reserve("user", (0.5, 5), 0)
    assert (await quota_db.snapshot("user", (0.5, 5)))["five_hour"]["blocked"]


async def test_system_role_budget_update_preserves_permissions_and_unlimited_concurrency(
    quota_db, monkeypatch
):
    from unittest.mock import AsyncMock

    from bson import ObjectId

    from src.infra.role.storage import RoleStorage
    from src.kernel.schemas.role import RoleQuotaUpdate

    storage = RoleStorage()
    storage._collection = quota_db.collection.database["roles"]
    role_id = ObjectId()
    await storage.collection.insert_one(
        {
            "_id": role_id,
            "name": "admin",
            "is_system": True,
            "permissions": ["chat:read"],
            "limits": None,
        }
    )
    monkeypatch.setattr(storage, "invalidate_cache", AsyncMock())
    role = await storage.update_usage_quota(
        str(role_id), RoleQuotaUpdate(five_hour_budget_usd=1, weekly_budget_usd=5)
    )
    assert role.is_system
    assert role.permissions == ["chat:read"]
    assert role.limits.five_hour_budget_usd == 1
    assert role.limits.max_concurrent_chats is None
    role = await storage.update_usage_quota(
        str(role_id), RoleQuotaUpdate(five_hour_budget_usd=None)
    )
    assert role.limits.five_hour_budget_usd is None
    assert role.limits.weekly_budget_usd == 5


async def test_five_hour_window_starts_on_use_not_view_and_survives_midnight(quota_db):
    start = datetime(2026, 10, 18, 14, 30, tzinfo=UTC)
    unused = await quota_db.snapshot("user", (1, 5), now=start)
    assert unused["five_hour"]["reset_at"] is None
    assert await quota_db.collection.find_one({"_id": "user"}) is None
    call = await quota_db.reserve("user", (1, 5), 0.3, now=start)
    await quota_db.settle(call, 0.3)
    later = await quota_db.reserve("user", (1, 5), 0.2, now=start + timedelta(hours=4))
    assert later["periods"][0] == call["periods"][0]
    await quota_db.settle(later, 0.2)
    active = await quota_db.snapshot("user", (1, 5), now=start + timedelta(hours=4))
    assert active["five_hour"]["used_usd"] == 0.5
    assert active["five_hour"]["reset_at"] == "2026-10-19T03:30:00+08:00"
    expired = await quota_db.snapshot("user", (1, 5), now=start + timedelta(hours=5))
    assert expired["five_hour"]["used_usd"] == 0
    assert expired["five_hour"]["reset_at"] is None
    new = await quota_db.reserve("user", (1, 5), 0.1, now=start + timedelta(hours=7))
    assert new["periods"][0] != call["periods"][0]


async def test_week_starts_on_use_survives_monday_and_restarts_independently(quota_db):
    start = datetime(2026, 10, 18, 14, 30, tzinfo=UTC)
    unused = await quota_db.snapshot("user", (1, 5), now=start)
    assert unused["weekly"]["reset_at"] is None
    assert await quota_db.collection.find_one({"_id": "user"}) is None
    first = await quota_db.reserve("user", (1, 5), 0.3, now=start)
    await quota_db.settle(first, 0.3)
    restarted = UsageQuota(quota_db.collection)
    monday = start + timedelta(days=1)
    later = await restarted.reserve("user", (1, 5), 0.2, now=monday)
    assert later["periods"][0] != first["periods"][0]
    assert later["periods"][1] == first["periods"][1]
    await restarted.settle(later, 0.2)
    active = await restarted.snapshot("user", (1, 5), now=monday)
    assert active["weekly"]["used_usd"] == 0.5
    assert active["weekly"]["reset_at"] == "2026-10-25T22:30:00+08:00"
    expired = await restarted.snapshot("user", (1, 5), now=start + timedelta(days=7))
    assert expired["weekly"]["used_usd"] == 0
    assert expired["weekly"]["reset_at"] is None
    assert (await quota_db.collection.find_one({"_id": "user"}))["weekly"]["key"] == first[
        "periods"
    ][1]
    next_use = start + timedelta(days=9, hours=2)
    fresh = await restarted.reserve("user", (1, 5), 0.1, now=next_use)
    assert fresh["periods"][1] != first["periods"][1]
    assert (await restarted.snapshot("user", (1, 5), now=next_use))["weekly"][
        "reset_at"
    ] == "2026-11-04T00:30:00+08:00"


async def test_concurrent_first_week_and_rollover_preserve_original_settlement(quota_db):
    start = datetime(2026, 10, 18, 14, 30, tzinfo=UTC)
    calls = await asyncio.gather(
        *(quota_db.reserve("user", (1, 5), 0.1, now=start) for _ in range(8))
    )
    assert len({call["periods"][1] for call in calls}) == 1
    other = await quota_db.reserve("other", (1, 5), 0.1, now=start + timedelta(hours=1))
    assert other["periods"][1] != calls[0]["periods"][1]
    new_time = start + timedelta(days=8)
    new = await quota_db.reserve("user", (1, 5), 0.2, now=new_time)
    await quota_db.settle(calls[0], 0.05)
    await quota_db.settle(calls[0], 0.05)
    doc = await quota_db.collection.find_one({"_id": "user"})
    assert doc["periods"][calls[0]["periods"][1]]["used"] == 50_000_000
    await quota_db.settle(new, 0.15)
    current = await quota_db.snapshot("user", (1, 5), now=new_time)
    assert current["weekly"]["used_usd"] == 0.15
    assert current["weekly"]["reserved_usd"] == 0


async def test_unknown_pending_reservation_allows_new_limits_and_can_release_once(quota_db):
    call = await quota_db.reserve("user", (None, None), None)
    allowed = await quota_db.reserve("user", (1, 5), 0)
    await quota_db.settle(allowed, 0)
    await quota_db.settle(call, None)
    await quota_db.settle(call, 0)
    await quota_db.settle(call, 0)
    snapshot = await quota_db.snapshot("user", (1, 5))
    assert not snapshot["weekly"]["unknown"]
    assert snapshot["weekly"]["used_usd"] == 0
    assert snapshot["weekly"]["reserved_usd"] == 0


async def test_stale_window_admission_rechecks_new_window_budget(quota_db, monkeypatch):
    start = datetime(2026, 10, 18, 14, 30, tzinfo=UTC)
    first = await quota_db.reserve("user", (1, 5), 0.1, now=start)
    await quota_db.settle(first, 0.1)
    selected, resume = asyncio.Event(), asyncio.Event()
    original = quota_db._active_windows

    async def pause_old_selection(user_id, now):
        windows = await original(user_id, now)
        if now == start + timedelta(hours=4):
            selected.set()
            await resume.wait()
        return windows

    monkeypatch.setattr(quota_db, "_active_windows", pause_old_selection)
    stale = asyncio.create_task(
        quota_db.reserve("user", (1, 5), 0.3, now=start + timedelta(hours=4))
    )
    await asyncio.wait_for(selected.wait(), 3)
    try:
        current = await quota_db.reserve("user", (1, 5), 0.8, now=start + timedelta(hours=6))
        await quota_db.settle(current, 1)
    finally:
        resume.set()
    with pytest.raises(AppError) as denied:
        await stale
    assert denied.value.error_code is ErrorCode.USAGE_QUOTA_EXCEEDED


async def test_reserve_prunes_expired_unknown_calls_without_viewing_snapshot(quota_db):
    start = datetime(2026, 10, 18, 14, 30, tzinfo=UTC)
    old = await quota_db.reserve("user", (None, None), 0.1, now=start)
    await quota_db.settle(old, None)
    pending = await quota_db.reserve("user", (None, None), 0.1, now=start)
    fresh = await quota_db.reserve("user", (1, 5), 0.1, now=start + timedelta(days=8))
    doc = await quota_db.collection.find_one({"_id": "user"})
    assert old["id"] not in doc["calls"]
    assert pending["id"] in doc["calls"]
    await quota_db.settle(pending, 0.05)
    doc = await quota_db.collection.find_one({"_id": "user"})
    assert doc["periods"][pending["periods"][1]]["used"] == 50_000_000
    await quota_db.settle(fresh, 0.1)


async def test_cancelled_lost_ack_keeps_unknown_visible_without_blocking_limits(quota_db):
    committed, wait_forever = asyncio.Event(), asyncio.Event()
    original = quota_db.collection

    class LostAcknowledgement:
        def __getattr__(self, name):
            return getattr(original, name)

        async def find_one_and_update(self, query, update, **kwargs):
            result = await original.find_one_and_update(query, update, **kwargs)
            if isinstance(update, dict) and any(
                path.startswith("calls.") for path in update.get("$set", {})
            ):
                committed.set()
                await wait_forever.wait()
            return result

    interrupted = UsageQuota(LostAcknowledgement())
    task = asyncio.create_task(interrupted.reserve("user", (None, None), None))
    try:
        await asyncio.wait_for(committed.wait(), 3)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    allowed = await quota_db.reserve("user", (1, 5), 0)
    await quota_db.settle(allowed, 0)
    doc = await original.find_one({"_id": "user"})
    ticket = next(iter(doc["calls"].values()))
    await quota_db.settle(ticket, 0)


async def test_quota_denial_reports_window_and_reason(quota_db):
    call = await quota_db.reserve("user", (1, 5), 0.8)
    await quota_db.settle(call, 1)
    with pytest.raises(AppError) as denied:
        await quota_db.reserve("user", (1, 5), 0.3)
    assert denied.value.args_data["windows"] == ["five_hour"]
    assert denied.value.args_data["reason"] == "exhausted"


async def test_orphan_pending_cleanup_keeps_late_grace_and_context(quota_db):
    start = datetime(2026, 10, 18, 14, 30, tzinfo=UTC)
    call = await quota_db.reserve(
        "user", (None, None), 0.1, now=start, context={"trace_id": "trace"}
    )
    doc = await quota_db.collection.find_one({"_id": "user"})
    assert doc["calls"][call["id"]]["context"] == {"trace_id": "trace"}
    assert doc["calls"][call["id"]]["pending"] is True
    assert doc["calls"][call["id"]]["created_at"] == start
    await quota_db.reserve("user", (None, None), 0.1, now=start + timedelta(days=8))
    doc = await quota_db.collection.find_one({"_id": "user"})
    assert call["id"] in doc["calls"]
    await quota_db.reserve("user", (None, None), 0.1, now=start + timedelta(days=15))
    doc = await quota_db.collection.find_one({"_id": "user"})
    assert call["id"] not in doc["calls"]


async def test_lost_reservation_ack_can_release_proved_unstarted_call_once(quota_db):
    original = quota_db.collection
    call_id = uuid.uuid4().hex

    class LostAcknowledgement:
        def __getattr__(self, name):
            return getattr(original, name)

        async def find_one_and_update(self, query, update, **kwargs):
            result = await original.find_one_and_update(query, update, **kwargs)
            if isinstance(update, dict) and f"calls.{call_id}" in update.get("$set", {}):
                raise RuntimeError("lost reservation acknowledgement")
            return result

    interrupted = UsageQuota(LostAcknowledgement())
    with pytest.raises(AppError) as unavailable:
        await interrupted.reserve("user", (None, None), None, call_id=call_id)
    assert unavailable.value.error_code is ErrorCode.USAGE_QUOTA_UNAVAILABLE
    doc = await original.find_one({"_id": "user"})
    assert call_id in doc["calls"]
    await quota_db.cancel_unstarted("user", call_id)
    await quota_db.cancel_unstarted("user", call_id)
    snapshot = await quota_db.snapshot("user", (1, 5))
    assert snapshot["five_hour"]["reserved_usd"] == 0
    assert snapshot["five_hour"]["used_usd"] == 0
    assert not snapshot["five_hour"]["unknown"]
    assert not snapshot["weekly"]["unknown"]


@pytest.mark.parametrize("call_id", ["call.id", "$call", "", "x" * 32])
async def test_caller_supplied_reservation_identity_rejects_unsafe_paths(quota_db, call_id):
    with pytest.raises(ValueError):
        await quota_db.reserve("user", (1, 5), 0.1, call_id=call_id)
    with pytest.raises(ValueError):
        await quota_db.cancel_unstarted("user", call_id)
    assert await quota_db.collection.find_one({"_id": "user"}) is None


async def test_duplicate_reservation_identity_never_adds_a_second_hold(quota_db):
    call_id = uuid.uuid4().hex
    ticket = await quota_db.reserve("user", (1, 5), 0.2, call_id=call_id)
    with pytest.raises(AppError) as duplicate:
        await quota_db.reserve("user", (1, 5), 0.2, call_id=call_id)
    assert duplicate.value.error_code is ErrorCode.USAGE_QUOTA_UNAVAILABLE
    assert (await quota_db.snapshot("user", (1, 5)))["five_hour"]["reserved_usd"] == 0.2
    await quota_db.settle(ticket, 0.1)


async def test_known_hot_call_uses_four_ledger_commands_including_settlement(quota_db):
    original = quota_db.collection
    commands = []

    class CountedCollection:
        def __getattr__(self, name):
            value = getattr(original, name)
            if name not in {"update_one", "find_one", "find_one_and_update"}:
                return value

            async def counted(*args, **kwargs):
                commands.append(name)
                return await value(*args, **kwargs)

            return counted

    ledger = UsageQuota(CountedCollection())
    initial = await ledger.reserve("user", (1, 5), 0.1)
    await ledger.settle(initial, 0.01)
    commands.clear()
    call = await ledger.reserve("user", (1, 5), 0.1)
    await ledger.settle(call, 0.01)
    assert commands == ["find_one_and_update", "update_one", "find_one_and_update", "update_one"]
    assert (await quota_db.snapshot("user", (1, 5)))["five_hour"]["used_usd"] == 0.02


async def test_known_call_latency_sample_keeps_exact_totals(quota_db):
    from statistics import median
    from time import perf_counter

    samples = []
    for _ in range(128):
        started = perf_counter()
        call = await quota_db.reserve("user", (1, 5), 0.0001)
        await quota_db.settle(call, 0.00001)
        samples.append((perf_counter() - started) * 1000)
    samples.sort()
    print(
        f"quota ledger 128 reserve+settle calls: median={median(samples):.2f}ms p95={samples[121]:.2f}ms"
    )
    snapshot = await quota_db.snapshot("user", (1, 5))
    assert snapshot["five_hour"]["used_usd"] == 0.00128
    assert snapshot["weekly"]["used_usd"] == 0.00128
    assert snapshot["weekly"]["reserved_usd"] == 0
    assert not snapshot["weekly"]["unknown"]
    assert (await quota_db.collection.find_one({"_id": "user"}))["calls"] == {}


async def test_partial_receipt_charges_now_and_final_receipt_only_adds_difference(quota_db):
    ticket = await quota_db.reserve("user", (1, 10), 0)
    await asyncio.gather(*(quota_db.settle(ticket, 0.2, partial=True) for _ in range(4)))
    snapshot = await quota_db.snapshot("user", (1, 10))
    assert snapshot["five_hour"]["used_usd"] == 0.2
    assert snapshot["five_hour"]["unknown"]
    await quota_db.settle(ticket, None)
    assert (await quota_db.snapshot("user", (1, 10)))["five_hour"]["used_usd"] == 0.2
    await asyncio.gather(
        quota_db.settle(ticket, 0.3),
        quota_db.settle(ticket, 0.3),
        quota_db.settle(ticket, 0.2, partial=True),
    )
    snapshot = await quota_db.snapshot("user", (1, 10))
    assert snapshot["five_hour"]["used_usd"] == 0.3
    assert not snapshot["five_hour"]["unknown"]


async def test_partial_then_reset_keeps_late_difference_in_original_periods(quota_db):
    from src.infra.usage.reset import QuotaReset

    ticket = await quota_db.reserve("user", (1, 10), 0)
    await quota_db.settle(ticket, 0.2, partial=True)
    await QuotaReset(quota_db.collection).reset(
        "user", "admin", "weekly", str(uuid.uuid4()), (1, 10)
    )
    await quota_db.settle(ticket, 0.3)
    snapshot = await quota_db.snapshot("user", (1, 10))
    assert snapshot["five_hour"]["used_usd"] == snapshot["weekly"]["used_usd"] == 0
    doc = await quota_db.collection.find_one({"_id": "user"})
    assert all(doc["periods"][key]["used"] == 300_000_000 for key in ticket["periods"])


async def test_mixed_model_settlement_receipts_match_quota_and_survive_replay(quota_db):
    from unittest.mock import AsyncMock

    from langchain_core.messages import AIMessage

    from src.infra.agent.events.processor import AgentEventProcessor
    from src.infra.llm.quota import QuotaChatMixin
    from src.infra.pricing.calculator import PriceRates
    from src.infra.writer.present import create_presenter

    presenter = create_presenter(session_id="s", agent_id="search", model="primary", model_id="p")
    presenter.emit = AsyncMock()
    processor = AgentEventProcessor(presenter)
    model = QuotaChatMixin()
    message = AIMessage(
        content="ok",
        usage_metadata={"input_tokens": 1000, "output_tokens": 0, "total_tokens": 1000},
    )
    for name, rate in [("primary", 10), ("fallback", 1)]:
        reservation = await quota_db.reserve(
            "user",
            (1, 10),
            0,
            context={"model": name, "model_config_id": name, "provider": "openai"},
        )
        ticket = (quota_db, reservation, PriceRates(input=rate, output=1), processor)
        await model._quota_finish(ticket, message, partial=name == "fallback")
        if name == "fallback":
            await model._quota_finish(ticket, message)
            await model._quota_finish(ticket, message)
    usage = presenter.emit.call_args.args[0]["data"]
    snapshot = await quota_db.snapshot("user", (1, 10))
    assert usage["cost_units"] == 11_000_000
    assert usage["cost_usd"] == snapshot["five_hour"]["used_usd"] == 0.011
    assert usage["cost_complete"] is True
    assert {item["model"] for item in usage["actual_models"]} == {"primary", "fallback"}
