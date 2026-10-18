"""Restartable bulk grants exercise real Mongo claims and per-account issuance."""

import asyncio
import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bson import ObjectId

from src.kernel.errors import AppError, ErrorCode


@pytest.fixture
async def batch_db(monkeypatch):
    if os.environ.get("LAMBCHAT_QUOTA_INTEGRATION") != "1":
        pytest.skip("Set LAMBCHAT_QUOTA_INTEGRATION=1 for disposable Mongo batch tests")
    from pymongo import AsyncMongoClient

    from src.infra import websocket
    from src.infra.storage.mongodb import build_mongo_connection_string

    monkeypatch.setattr(
        websocket,
        "get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=AsyncMock()),
    )

    client = AsyncMongoClient(
        build_mongo_connection_string(), serverSelectionTimeoutMS=3000, tz_aware=True
    )
    db = client[f"test_lambchat_reset_batches_{uuid.uuid4().hex}"]
    try:
        await client.admin.command("ping")
        yield db
    finally:
        await client.drop_database(db.name)
        await client.close()


def service(db):
    from src.infra.usage.reset_batches import ResetCardBatches

    return ResetCardBatches(db)


async def add_users(db, count):
    users = [
        {"_id": ObjectId(), "is_active": i % 2 == 0, "created_at": datetime.now(UTC)}
        for i in range(count)
    ]
    if users:
        users[0].pop("created_at")  # Existing legacy users must remain eligible.
        await db.users.insert_many(users)
    return users


async def finish(db, batch_id, actor="admin"):
    for _ in range(100):
        result = await service(db).advance(batch_id, actor)
        assert result["issued"] + result["failed"] == result["processed"]
        if result["status"] == "completed":
            return result
    pytest.fail("Batch did not finish within bounded advance calls")


@pytest.mark.parametrize("window", ["five_hour", "weekly"])
async def test_restartable_batches_include_inactive_and_legacy_but_exclude_later_users(
    batch_db, window
):
    db = batch_db
    users = await add_users(db, 53)
    key = str(uuid.uuid4())
    initial = await service(db).create("admin", key, window)
    assert initial["status"] == "preparing" and initial["processed"] == 0
    await db.users.insert_one({"_id": ObjectId(), "created_at": datetime.now(UTC)})
    first = await service(db).advance(key, "admin")
    assert first["status"] == "preparing"
    assert await db.quota_reset_card_batch_recipients.count_documents({}) <= 25
    result = await finish(db, key)
    assert (result["total"], result["processed"], result["issued"], result["failed"]) == (
        53,
        53,
        53,
        0,
    )
    for user in users:
        doc = await db.user_usage_quotas.find_one({"_id": str(user["_id"])})
        assert len(doc["reset_cards"]) == 1
        card = next(iter(doc["reset_cards"].values()))
        assert card["window"] == window and card["granted_by"] == "admin"
        assert card["expires_at"] - card["granted_at"] == timedelta(days=30)
        assert (await db.users.find_one({"_id": user["_id"]}))["is_active"] == user["is_active"]
    assert await db.user_usage_quotas.count_documents({}) == 53
    assert (await service(db).latest("admin", 1))["items"][0] == result
    assert await service(db).latest("other", 1) == {"items": []}


async def test_batch_key_payload_and_owner_are_immutable(batch_db):
    db = batch_db
    await add_users(db, 1)
    key = str(uuid.uuid4())
    first, second = await asyncio.gather(
        service(db).create("admin", key, "weekly"), service(db).create("admin", key, "weekly")
    )
    assert first["id"] == second["id"] == key
    assert await db.quota_reset_card_batches.count_documents({}) == 1
    for actor, window in [("admin", "five_hour"), ("other", "weekly")]:
        with pytest.raises(AppError) as error:
            await service(db).create(actor, key, window)
        assert error.value.error_code is ErrorCode.CONFLICT
    for method in [service(db).get, service(db).advance]:
        with pytest.raises(AppError) as error:
            await method(key, "other")
        assert error.value.error_code is ErrorCode.NOT_FOUND


async def test_simultaneous_advances_do_not_duplicate_cards_or_counters(batch_db):
    db = batch_db
    await add_users(db, 31)
    key = str(uuid.uuid4())
    await service(db).create("admin", key, "weekly")
    for _ in range(6):
        await asyncio.gather(*(service(db).advance(key, "admin") for _ in range(6)))
    result = await finish(db, key)
    assert (result["issued"], result["failed"], result["processed"]) == (31, 0, 31)
    async for doc in db.user_usage_quotas.find({}):
        assert len(doc["reset_cards"]) == len(doc["reset_operations"]) == 1
    assert await service(db).advance(key, "admin") == result


async def test_retry_after_issuance_response_loss_uses_same_operation(batch_db, monkeypatch):
    from src.infra.usage.reset import QuotaReset

    db = batch_db
    await add_users(db, 1)
    key = str(uuid.uuid4())
    await service(db).create("admin", key, "weekly")
    await service(db).advance(key, "admin")  # Persist preparation before issuance.
    original = QuotaReset.issue_card

    async def lose_response(self, *args, **kwargs):
        await original(self, *args, **kwargs)
        raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE)

    monkeypatch.setattr(QuotaReset, "issue_card", lose_response)
    with pytest.raises(AppError):
        await service(db).advance(key, "admin")
    monkeypatch.setattr(QuotaReset, "issue_card", original)
    result = await finish(db, key)
    assert result["issued"] == 1 and result["failed"] == 0
    doc = await db.user_usage_quotas.find_one({})
    assert len(doc["reset_cards"]) == 1


async def test_expired_lease_recovers_preparation_and_errors_are_bounded(batch_db):
    from src.infra.usage.reset import QuotaReset

    db = batch_db
    users = await add_users(db, 24)
    key = str(uuid.uuid4())
    await service(db).create("admin", key, "five_hour")
    await db.quota_reset_card_batches.update_one(
        {"_id": key},
        {
            "$set": {
                "lease_token": "dead-process",
                "lease_until": datetime.now(UTC) - timedelta(seconds=1),
            }
        },
    )
    await service(db).advance(key, "admin")
    # Seed the real card cap without 2,400 unrelated issuance operations.
    now = datetime.now(UTC)
    cards = {
        str(i): {
            "id": str(i),
            "status": "available",
            "granted_at": now,
            "expires_at": now + timedelta(days=1),
        }
        for i in range(100)
    }
    for user in users:
        await db.user_usage_quotas.insert_one({"_id": str(user["_id"]), "reset_cards": cards})
    result = await finish(db, key)
    assert (result["total"], result["issued"], result["failed"]) == (24, 0, 24)
    assert 0 < len(result["errors"]) <= 20
    assert {error["code"] for error in result["errors"]} == {"conflict"}
    assert await db.quota_reset_card_batch_recipients.count_documents({"status": "failed"}) == 24
    assert (await QuotaReset(db.user_usage_quotas).credits(str(users[0]["_id"])))[
        "available_count"
    ] == 100


async def test_ancient_uncertain_recipient_never_reissues_after_operation_pruned(batch_db):
    db = batch_db
    await add_users(db, 1)
    key = str(uuid.uuid4())
    await service(db).create("admin", key, "weekly")
    await service(db).advance(key, "admin")
    await db.quota_reset_card_batch_recipients.update_one(
        {"batch_id": key},
        {"$set": {"status": "issuing", "issuing_at": datetime.now(UTC) - timedelta(days=38)}},
    )
    result = await finish(db, key)
    assert result["failed"] == 1 and result["issued"] == 0
    assert await db.user_usage_quotas.count_documents({}) == 0


async def test_batch_routes_validate_permission_payload_and_owner(batch_db, monkeypatch):
    import httpx
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    from src.api.deps import get_current_user_required
    from src.api.routes import usage
    from src.infra.usage import reset_batches
    from src.kernel.schemas.user import TokenPayload

    db = batch_db
    await add_users(db, 2)
    real_service = service(db)
    monkeypatch.setattr(reset_batches, "ResetCardBatches", lambda: real_service)
    app = FastAPI()
    app.include_router(usage.router, prefix="/api/usage")
    actor = TokenPayload(sub="admin", username="Admin", permissions=[])
    app.dependency_overrides[get_current_user_required] = lambda: actor

    @app.exception_handler(AppError)
    async def error_handler(request, error):
        return JSONResponse(
            {"detail": {"code": error.error_code.code}}, status_code=error.http_status
        )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        key = str(uuid.uuid4())
        path = "/api/usage/quota/reset-card-batches"
        body = {"idempotency_key": key, "window": "weekly"}
        assert (await client.post(path, json=body)).status_code == 403
        assert (await client.get(path)).status_code == 403
        assert (await client.get(f"{path}/{key}")).status_code == 403
        assert (await client.post(f"{path}/{key}/advance")).status_code == 403
        actor.permissions = ["usage:admin"]
        assert (await client.post(path, json={"idempotency_key": key})).status_code == 422
        assert (await client.post(path, json={**body, "window": "all"})).status_code == 422
        assert (await client.post(path, json={**body, "user_ids": []})).status_code == 422
        assert (await client.post(path, json=body)).json()["id"] == key
        assert (await client.get(f"{path}/{key}")).json()["status"] == "preparing"
        assert (await client.post(f"{path}/{key}/advance")).status_code == 200
        result = await client.post(f"{path}/{key}/advance")
        assert result.json()["issued"] == 2
        assert (await client.get(path, params={"limit": 1})).json()["items"] == [result.json()]
        actor.sub = "other"
        assert (await client.get(f"{path}/{key}")).status_code == 404
        assert (await client.post(f"{path}/{key}/advance")).status_code == 404
        assert (await client.get(path)).json() == {"items": []}


async def test_expired_lease_fences_late_worker_and_recovers_terminal_counters(
    batch_db, monkeypatch
):
    from src.infra.usage.reset import QuotaReset

    db = batch_db
    await add_users(db, 1)
    key = str(uuid.uuid4())
    await service(db).create("admin", key, "weekly")
    await service(db).advance(key, "admin")
    committed, release = asyncio.Event(), asyncio.Event()
    original = QuotaReset.issue_card
    first = True

    async def suspend_first_response(self, *args, **kwargs):
        nonlocal first
        result = await original(self, *args, **kwargs)
        if first:
            first = False
            committed.set()
            await release.wait()
        return result

    monkeypatch.setattr(QuotaReset, "issue_card", suspend_first_response)
    late_worker = asyncio.create_task(service(db).advance(key, "admin"))
    try:
        await asyncio.wait_for(committed.wait(), 3)
        await db.quota_reset_card_batches.update_one(
            {"_id": key}, {"$set": {"lease_until": datetime.now(UTC) - timedelta(seconds=1)}}
        )
        current = await service(db).advance(key, "admin")
        assert current["status"] == "completed" and current["issued"] == 1
    finally:
        release.set()
        await late_worker
    recipient = await db.quota_reset_card_batch_recipients.find_one({"batch_id": key})
    quota = await db.user_usage_quotas.find_one({})
    assert list(quota["reset_cards"]) == [recipient["credit_id"]]
    assert recipient["created_at"] <= recipient["issuing_at"] <= recipient["updated_at"]
    # Simulate a process dying after its recipient commit and before summary commit.
    await db.quota_reset_card_batches.update_one(
        {"_id": key}, {"$set": {"status": "running", "processed": 0, "issued": 0}}
    )
    result = await service(db).advance(key, "admin")
    assert result["processed"] == result["issued"] == 1
    assert result["status"] == "completed"
    assert len((await db.user_usage_quotas.find_one({}))["reset_cards"]) == 1


async def test_preparation_replay_after_cursor_write_loss_deduplicates_recipients(
    batch_db, monkeypatch
):
    db = batch_db
    await add_users(db, 29)
    key = str(uuid.uuid4())
    worker = service(db)
    await worker.create("admin", key, "five_hour")
    original = worker.batches.update_one

    async def fail_cursor_update(query, update, **kwargs):
        if "cursor" in update.get("$set", {}):
            raise OSError("lost preparation cursor write")
        return await original(query, update, **kwargs)

    monkeypatch.setattr(worker.batches, "update_one", fail_cursor_update)
    with pytest.raises(AppError):
        await worker.advance(key, "admin")
    assert await db.quota_reset_card_batch_recipients.count_documents({}) == 25
    result = await finish(db, key)
    assert (result["total"], result["issued"], result["failed"]) == (29, 29, 0)
    assert await db.quota_reset_card_batch_recipients.count_documents({}) == 29


@pytest.mark.parametrize("delivery_fails", [False, True])
async def test_bulk_notification_follows_durable_issue_and_terminal_replay_never_reissues(
    batch_db, monkeypatch, delivery_fails
):
    from src.infra import websocket

    db = batch_db
    users = await add_users(db, 1)
    target = str(users[0]["_id"])
    delivered = []

    async def deliver(user_id, message):
        recipient = await db.quota_reset_card_batch_recipients.find_one({"user_id": user_id})
        assert recipient["status"] == "issued" and recipient["credit_id"]
        batch = await db.quota_reset_card_batches.find_one({"_id": recipient["batch_id"]})
        assert "lease_token" not in batch and "lease_until" not in batch
        delivered.append((user_id, message))
        if delivery_fails:
            raise OSError("notification transport unavailable")

    monkeypatch.setattr(
        websocket,
        "get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=deliver),
    )
    key = str(uuid.uuid4())
    await service(db).create("admin", key, "weekly")
    result = await finish(db, key)
    assert delivered == [(target, {"type": "usage_quota_updated"})]
    assert result["issued"] == 1 and result["failed"] == 0
    assert await service(db).advance(key, "admin") == result
    assert len(delivered) == 1
    assert len((await db.user_usage_quotas.find_one({"_id": target}))["reset_cards"]) == 1


async def test_partial_chunk_failure_still_notifies_already_committed_recipient(
    batch_db, monkeypatch
):
    from src.infra import websocket
    from src.infra.usage.reset import QuotaReset

    db = batch_db
    await add_users(db, 2)
    notified = []

    async def deliver(user_id, message):
        notified.append(user_id)

    monkeypatch.setattr(
        websocket,
        "get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=deliver),
    )
    original = QuotaReset.issue_card
    calls = 0

    async def fail_second(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE)
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(QuotaReset, "issue_card", fail_second)
    key = str(uuid.uuid4())
    await service(db).create("admin", key, "weekly")
    await service(db).advance(key, "admin")
    with pytest.raises(AppError):
        await service(db).advance(key, "admin")
    issued = await db.quota_reset_card_batch_recipients.find_one({"status": "issued"})
    assert notified == [issued["user_id"]]
    result = await finish(db, key)
    assert result["issued"] == 2 and len(set(notified)) == 2
