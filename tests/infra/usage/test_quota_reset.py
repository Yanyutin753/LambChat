"""Reset cards use the account ledger atomically, with no billing-history edits."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from src.infra.usage.quota import UsageQuota
from src.kernel.errors import AppError, ErrorCode


@pytest.fixture
async def reset_db():
    if os.environ.get("LAMBCHAT_QUOTA_INTEGRATION") != "1":
        pytest.skip("Set LAMBCHAT_QUOTA_INTEGRATION=1 for disposable Mongo reset tests")
    from pymongo import AsyncMongoClient

    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.infra.usage.reset import QuotaReset

    client = AsyncMongoClient(
        build_mongo_connection_string(), serverSelectionTimeoutMS=3000, tz_aware=True
    )
    db = client[f"test_lambchat_quota_reset_{uuid.uuid4().hex}"]
    try:
        await client.admin.command("ping")
        yield QuotaReset(db["quotas"]), UsageQuota(db["quotas"])
    finally:
        await client.drop_database(db.name)
        await client.close()


def test_reset_requests_require_uuid_idempotency_and_valid_scope():
    from pydantic import ValidationError

    from src.kernel.schemas.usage_quota import QuotaResetRequest, ResetCardConsumeRequest

    with pytest.raises(ValidationError):
        QuotaResetRequest(window="five_hour", idempotency_key="untrusted.path")
    with pytest.raises(ValidationError):
        QuotaResetRequest(window="all", idempotency_key=uuid.uuid4())
    with pytest.raises(ValidationError):
        ResetCardConsumeRequest(idempotency_key=uuid.uuid4(), user_id="victim")


async def _exhaust(ledger, budgets=(1, 5), *, now=None):
    call = await ledger.reserve("user", budgets, 1, now=now)
    await ledger.settle(call, 1)
    return call


async def test_admin_reset_rotates_one_anchor_and_late_usage_stays_in_original_period(reset_db):
    resets, ledger = reset_db
    call = await _exhaust(ledger)
    pending = await ledger.reserve("user", (10, 10), 0.2)
    operation = str(uuid.uuid4())
    result = await resets.reset("user", "admin", "five_hour", operation, (1, 5))
    assert result["outcome"] == "reset"
    snapshot = await ledger.snapshot("user", (1, 5))
    assert snapshot["five_hour"]["reset_at"] is not None
    assert snapshot["weekly"]["used_usd"] == 1
    fresh = await ledger.reserve("user", (1, 5), 0.1)
    assert fresh["periods"][0] != call["periods"][0]
    assert fresh["periods"][1] == call["periods"][1]
    await ledger.settle(pending, 0.15)
    assert (await ledger.snapshot("user", (1, 5)))["five_hour"]["used_usd"] == 0
    replay = await resets.reset("user", "admin", "five_hour", operation, (1, 5))
    assert replay["outcome"] == "alreadyRedeemed"
    doc = await ledger.collection.find_one({"_id": "user"})
    audit = doc["reset_operations"][operation]
    assert audit["actor_id"] == "admin" and audit["user_id"] == "user"
    assert audit["scope"] == ["five_hour"]
    with pytest.raises(AppError) as conflict:
        await resets.reset("user", "admin", "weekly", operation, (1, 5))
    assert conflict.value.error_code is ErrorCode.CONFLICT


async def test_card_issue_is_idempotent_and_only_account_owner_can_find_it(reset_db):
    resets, _ = reset_db
    operation = str(uuid.uuid4())
    issued = await asyncio.gather(
        *(resets.issue_card("user", "admin", operation) for _ in range(8))
    )
    assert {item["outcome"] for item in issued} == {"issued", "alreadyIssued"}
    assert len({item["credit_id"] for item in issued}) == 1
    assert (await resets.credits("user"))["available_count"] == 1
    assert (await resets.credits("other"))["available_count"] == 0


async def test_generic_card_resets_both_exhausted_windows_exactly_once(reset_db):
    resets, ledger = reset_db
    await _exhaust(ledger, (1, 1))
    card = await resets.issue_card("user", "admin", str(uuid.uuid4()))
    result = await asyncio.gather(
        *(
            resets.consume("user", str(uuid.uuid4()), (1, 1), credit_id=card["credit_id"])
            for _ in range(8)
        )
    )
    assert sum(item["outcome"] == "reset" for item in result) == 1
    assert (await resets.credits("user"))["available_count"] == 0
    snapshot = await ledger.snapshot("user", (1, 1))
    assert snapshot["five_hour"]["used_usd"] == snapshot["weekly"]["used_usd"] == 0
    assert snapshot["five_hour"]["reset_at"] and snapshot["weekly"]["reset_at"]


@pytest.mark.parametrize("state", ["reserved", "unknown", "zero", "unlimited", "unused"])
async def test_card_never_consumes_for_ineligible_limit(reset_db, state):
    resets, ledger = reset_db
    budgets = (0, None) if state == "zero" else (None, None) if state == "unlimited" else (1, None)
    if state in {"reserved", "unknown", "unlimited"}:
        call = await ledger.reserve("user", (None, None), 1)
        if state == "unknown":
            await ledger.settle(call, None)
        elif state == "unlimited":
            await ledger.settle(call, 1)
    await resets.issue_card("user", "admin", str(uuid.uuid4()))
    assert (await resets.consume("user", str(uuid.uuid4()), budgets))["outcome"] == "nothingToReset"
    assert (await resets.credits("user"))["available_count"] == 1


async def test_consume_replay_has_no_extra_rotation_or_credit_loss(reset_db):
    resets, ledger = reset_db
    await _exhaust(ledger)
    for _ in range(2):
        await resets.issue_card("user", "admin", str(uuid.uuid4()))
    operation = str(uuid.uuid4())
    first = await resets.consume("user", operation, (1, 5))
    replay = await resets.consume("user", operation, (1, 5))
    assert first["outcome"] == "reset" and replay["outcome"] == "alreadyRedeemed"
    assert (await resets.credits("user"))["available_count"] == 1


async def test_expired_card_cannot_reset_and_admin_can_clear_unknown_usage(reset_db):
    resets, ledger = reset_db
    start = datetime.now(UTC)
    await resets.issue_card("user", "admin", str(uuid.uuid4()), now=start - timedelta(days=31))
    assert (await resets.consume("user", str(uuid.uuid4()), (1, 5), now=start))[
        "outcome"
    ] == "noCredit"
    call = await ledger.reserve("user", (1, 5), 0.1)
    await ledger.settle(call, None)
    result = await resets.reset("user", "admin", "weekly", str(uuid.uuid4()), (1, 5))
    assert result["outcome"] == "reset"
    snapshot = await ledger.snapshot("user", (1, 5))
    assert not snapshot["five_hour"]["unknown"] and not snapshot["weekly"]["unknown"]


async def test_admin_cannot_reset_zero_or_empty_windows_and_card_limit_is_bounded(reset_db):
    resets, ledger = reset_db
    for budget in (0, None, 1):
        result = await resets.reset("user", "admin", "five_hour", str(uuid.uuid4()), (budget, None))
        assert result["outcome"] == "nothingToReset"
    for _ in range(100):
        await resets.issue_card("user", "admin", str(uuid.uuid4()))
    with pytest.raises(AppError) as denied:
        await resets.issue_card("user", "admin", str(uuid.uuid4()))
    assert denied.value.error_code is ErrorCode.CONFLICT
    assert (await resets.credits("user"))["available_count"] == 100


async def test_card_expiring_during_cas_retry_cannot_be_consumed(reset_db, monkeypatch):
    from src.infra.usage import reset

    resets, ledger = reset_db
    granted = datetime.now(UTC)
    expires = granted + timedelta(days=30)
    await resets.issue_card("user", "admin", str(uuid.uuid4()), now=granted)
    await _exhaust(ledger, now=expires - timedelta(seconds=1))

    class Clock:
        current = expires - timedelta(seconds=1)

        @classmethod
        def now(cls, tz):
            return cls.current

    class RaceCollection:
        retried = False

        def __getattr__(self, name):
            return getattr(ledger.collection, name)

        async def update_one(self, query, update, **kwargs):
            if not self.retried and any(
                key.startswith("reset_operations.") for key in update.get("$set", {})
            ):
                self.retried = True
                Clock.current = expires + timedelta(seconds=1)
                return SimpleNamespace(matched_count=0)
            return await ledger.collection.update_one(query, update, **kwargs)

    monkeypatch.setattr(reset, "datetime", Clock)
    result = await reset.QuotaReset(RaceCollection()).consume("user", str(uuid.uuid4()), (1, 5))
    assert result["outcome"] == "noCredit"
    doc = await ledger.collection.find_one({"_id": "user"})
    assert next(iter(doc["reset_cards"].values()))["status"] == "available"


async def test_weekly_card_resets_both_windows_from_redemption_time_and_preserves_old_calls(
    reset_db,
):
    resets, ledger = reset_db
    start = datetime.now(UTC)
    call = await ledger.reserve("user", (10, 10), 1, now=start)
    await ledger.settle(call, 0.5)
    pending = await ledger.reserve("user", (10, 10), 0.2, now=start)
    card = await resets.issue_card("user", "admin", str(uuid.uuid4()), window="weekly", now=start)
    assert (await resets.credits("user", now=start))["credits"][0]["window"] == "weekly"
    redeemed = start + timedelta(minutes=10)
    result = await resets.consume(
        "user", str(uuid.uuid4()), (10, 10), credit_id=card["credit_id"], now=redeemed
    )
    assert result["windows"] == ["five_hour", "weekly"]
    snapshot = await ledger.snapshot("user", (10, 10), now=redeemed)
    assert snapshot["five_hour"]["used_usd"] == snapshot["weekly"]["used_usd"] == 0
    assert abs(
        datetime.fromisoformat(snapshot["five_hour"]["reset_at"]) - redeemed - timedelta(hours=5)
    ) < timedelta(milliseconds=1)
    assert abs(
        datetime.fromisoformat(snapshot["weekly"]["reset_at"]) - redeemed - timedelta(days=7)
    ) < timedelta(milliseconds=1)
    await ledger.settle(pending, 0.1)
    snapshot = await ledger.snapshot("user", (10, 10), now=redeemed)
    assert snapshot["five_hour"]["used_usd"] == snapshot["weekly"]["used_usd"] == 0


async def test_five_hour_card_cannot_reset_weekly_usage_or_consume_for_unused_window(reset_db):
    resets, ledger = reset_db
    await _exhaust(ledger, (2, 2))
    card = await resets.issue_card("user", "admin", str(uuid.uuid4()), window="five_hour")
    result = await resets.consume("user", str(uuid.uuid4()), (2, 2), credit_id=card["credit_id"])
    assert result["windows"] == ["five_hour"]
    snapshot = await ledger.snapshot("user", (2, 2))
    assert snapshot["five_hour"]["used_usd"] == 0 and snapshot["weekly"]["used_usd"] == 1
    card = await resets.issue_card("user", "admin", str(uuid.uuid4()), window="five_hour")
    assert (await resets.consume("user", str(uuid.uuid4()), (2, 2), credit_id=card["credit_id"]))[
        "outcome"
    ] == "nothingToReset"
    assert (await resets.credits("user"))["available_count"] == 1


@pytest.mark.parametrize("window", ["five_hour", "weekly", None])
async def test_unknown_receipts_do_not_block_resetting_settled_spending(reset_db, window):
    resets, ledger = reset_db
    budgets = (1, 1)
    pending = await ledger.reserve("user", budgets, 0.1)
    await ledger.settle(pending, None)
    spent = await ledger.reserve("user", budgets, 1)
    await ledger.settle(spent, 1)
    card = await resets.issue_card("user", "admin", str(uuid.uuid4()), window=window)
    result = await resets.consume("user", str(uuid.uuid4()), budgets, credit_id=card["credit_id"])
    assert result["outcome"] == "reset"
    expected_windows = ["five_hour"] if window == "five_hour" else ["five_hour", "weekly"]
    assert result["windows"] == expected_windows
    assert (await resets.credits("user"))["available_count"] == 0
    snapshot = await ledger.snapshot("user", budgets)
    assert snapshot["five_hour"]["used_usd"] == 0
    assert snapshot["weekly"]["used_usd"] == (1 if window == "five_hour" else 0)
    await ledger.settle(pending, 0.2)
    snapshot = await ledger.snapshot("user", budgets)
    assert snapshot["five_hour"]["used_usd"] == 0
    assert snapshot["weekly"]["used_usd"] == (1.2 if window == "five_hour" else 0)


async def test_card_history_lists_actual_consumption_once_and_stays_account_local(reset_db):
    resets, ledger = reset_db
    now = datetime.now(UTC).replace(microsecond=0)
    await _exhaust(ledger, now=now)
    issued = await resets.issue_card(
        "user", "admin", str(uuid.uuid4()), window="five_hour", now=now
    )
    operation = str(uuid.uuid4())
    await resets.consume("user", operation, (1, 5), credit_id=issued["credit_id"], now=now)
    await resets.consume("user", operation, (1, 5), credit_id=issued["credit_id"], now=now)
    history = (await resets.credits("user", now=now))["history"]
    assert history == [{"id": issued["credit_id"], "window": "five_hour", "redeemed_at": now}]
    assert (await resets.credits("other", now=now))["history"] == []
    assert (await resets.credits("user", now=now + timedelta(days=37)))["history"] == []
