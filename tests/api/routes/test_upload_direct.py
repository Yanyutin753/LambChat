import hashlib
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.api.routes import upload
from src.api.routes import upload_direct as direct
from src.api.routes.file_type import FileCategory
from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError


@pytest.fixture
def env(monkeypatch):
    adapter = SimpleNamespace(
        config=SimpleNamespace(
            provider="aws", endpoint_url=None, region="us-east-1", bucket_name="files"
        ),
        create=AsyncMock(return_value="upload-id"),
        sign_part=AsyncMock(return_value="https://storage/part"),
        list_parts=AsyncMock(return_value=[{"PartNumber": 1, "ETag": "etag", "Size": 3}]),
        complete=AsyncMock(),
        abort=AsyncMock(),
    )

    async def stream(key):
        yield b"abc"

    storage = SimpleNamespace(
        direct_upload=adapter,
        is_local=False,
        get_size=AsyncMock(return_value=3),
        download_stream=stream,
        delete_file=AsyncMock(),
        file_exists=AsyncMock(return_value=True),
    )
    collection = SimpleNamespace(
        insert_one=AsyncMock(),
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
        find_one=AsyncMock(),
        find_one_and_update=AsyncMock(),
        delete_one=AsyncMock(),
        delete_many=AsyncMock(),
        create_index=AsyncMock(),
    )
    records = SimpleNamespace(
        create=AsyncMock(
            return_value={
                "key": "document/user/key",
                "name": "a.txt",
                "size": 3,
                "category": "document",
                "mime_type": "text/plain",
            }
        ),
        find_by_key=AsyncMock(return_value=None),
        schedule_owned_cleanup=AsyncMock(),
    )
    monkeypatch.setattr(direct, "tickets", lambda: collection)
    monkeypatch.setattr(upload, "get_or_init_storage", AsyncMock(return_value=storage))
    monkeypatch.setattr(
        upload, "validate_upload_metadata", AsyncMock(return_value=(FileCategory.DOCUMENT, 100))
    )
    monkeypatch.setattr(upload, "_file_record_storage", records)
    monkeypatch.setattr(upload, "_get_live_record_by_hash", AsyncMock(return_value=None))
    user = SimpleNamespace(sub="user", roles=[], permissions=["file:upload"])
    ticket = {
        "_id": "ticket",
        "owner": "user",
        "key": "document/user/key",
        "name": "a.txt",
        "size": 3,
        "mime_type": "text/plain",
        "category": "document",
        "upload_id": "upload-id",
        "state": "active",
        "storage": direct.storage_identity(storage),
        "expires_at": utc_now() + timedelta(hours=1),
    }
    collection.find_one.return_value = ticket
    collection.find_one_and_update.return_value = ticket
    return SimpleNamespace(
        storage=storage,
        adapter=adapter,
        collection=collection,
        records=records,
        user=user,
        ticket=ticket,
    )


@pytest.mark.asyncio
async def test_start_preserves_limits_and_returns_only_scoped_ticket(env):
    result = await direct.start_upload(direct.StartUpload(name="a.txt", size=3), env.user)
    assert result["mode"] == "direct" and result["part_count"] == 1
    assert "upload_id" not in result and "key" not in result
    doc = env.collection.insert_one.call_args.args[0]
    assert doc["owner"] == "user" and doc["key"].startswith("document/user/")
    env.adapter.create.assert_awaited_once()
    with pytest.raises(AppError):
        await direct.start_upload(direct.StartUpload(name="a.txt", size=101), env.user)
    assert env.adapter.create.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "local,name,mime", [(True, "a.txt", "text/plain"), (False, "a.tiff", "image/tiff")]
)
async def test_local_storage_and_model_unsafe_images_use_existing_proxy(
    env, local, name, mime, monkeypatch
):
    env.storage.is_local = local
    monkeypatch.setattr(
        upload, "validate_upload_metadata", AsyncMock(return_value=(FileCategory.IMAGE, 100))
    )
    assert await direct.start_upload(
        direct.StartUpload(name=name, mime_type=mime, size=3), env.user
    ) == {"mode": "proxy"}
    env.collection.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_permission_check_precedes_ticket_creation(env, monkeypatch):
    monkeypatch.setattr(
        upload, "validate_upload_metadata", AsyncMock(side_effect=HTTPException(403))
    )
    with pytest.raises(HTTPException):
        await direct.start_upload(direct.StartUpload(name="a.txt", size=3), env.user)
    env.collection.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_signing_rejects_missing_owner_out_of_range_and_expired_tickets(env):
    env.collection.find_one.return_value = None
    with pytest.raises(AppError):
        await direct.sign_part("ticket", 1, env.user)
    assert env.collection.find_one.call_args.args[0]["owner"] == "user"
    env.collection.find_one.return_value = env.ticket
    with pytest.raises(AppError):
        await direct.sign_part("ticket", 2, env.user)
    env.ticket["expires_at"] = utc_now() - timedelta(seconds=1)
    with pytest.raises(AppError):
        await direct.sign_part("ticket", 1, env.user)
    env.adapter.sign_part.assert_not_awaited()


@pytest.mark.asyncio
async def test_signatures_recheck_reduced_role_limits(env, monkeypatch):
    monkeypatch.setattr(
        upload, "validate_upload_metadata", AsyncMock(return_value=(FileCategory.DOCUMENT, 2))
    )
    with pytest.raises(AppError):
        await direct.sign_part("ticket", 1, env.user)
    env.adapter.sign_part.assert_not_awaited()


def request():
    return Request(
        {
            "type": "http",
            "method": "POST",
            "scheme": "https",
            "path": "/",
            "headers": [(b"host", b"app.example")],
        }
    )


@pytest.mark.asyncio
async def test_completion_hashes_storage_bytes_before_recording(env):
    env.collection.find_one.side_effect = [env.ticket, {"state": "completing"}]
    result = await direct.complete_upload("ticket", request(), env.user)
    assert result["key"] == env.ticket["key"]
    assert env.records.create.call_args.kwargs["file_hash"] == hashlib.sha256(b"abc").hexdigest()
    env.adapter.complete.assert_awaited_once()
    assert env.collection.update_one.call_args.args[1]["$set"]["state"] == "completed"


@pytest.mark.asyncio
async def test_completion_reuses_owned_dedupe_and_removes_new_object(env, monkeypatch):
    env.collection.find_one.side_effect = [env.ticket, {"state": "completing"}]
    existing = dict(env.records.create.return_value, key="document/user/existing")
    monkeypatch.setattr(upload, "_get_live_record_by_hash", AsyncMock(return_value=existing))
    result = await direct.complete_upload("ticket", request(), env.user)
    assert result["key"] == existing["key"]
    env.records.create.assert_not_awaited()
    env.storage.delete_file.assert_awaited_once_with(env.ticket["key"])


@pytest.mark.asyncio
async def test_invalid_parts_cannot_be_committed(env):
    env.adapter.list_parts.return_value[0]["Size"] = 4
    with pytest.raises(AppError):
        await direct.complete_upload("ticket", request(), env.user)
    env.records.create.assert_not_awaited()
    env.adapter.complete.assert_not_awaited()
    env.adapter.abort.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_during_hashing_prevents_record_and_deletes_object(env):
    env.collection.find_one.side_effect = [
        env.ticket,
        {"state": "completing", "cancel_requested": True},
    ]
    with pytest.raises(AppError):
        await direct.complete_upload("ticket", request(), env.user)
    env.records.create.assert_not_awaited()
    env.storage.delete_file.assert_awaited_once_with(env.ticket["key"])


@pytest.mark.asyncio
async def test_cancel_active_upload_aborts_provider_and_cleans_ticket(env):
    env.ticket["state"] = "cleanup"
    env.collection.find_one_and_update.side_effect = [None, env.ticket]
    await direct.cancel_upload("ticket", env.user)
    env.adapter.abort.assert_awaited_once_with(env.ticket["key"], "upload-id")
    env.collection.delete_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_cancel_flags_ticket_before_a_competing_completion_can_admit_it(env):
    current = dict(env.ticket)

    async def update(query, change, **kwargs):
        states = query.get("state", {}).get("$in")
        if states is not None and current["state"] not in states:
            # Completion wins the admission race after cancel's first state-filtered write.
            current["state"] = "completing"
            return None
        current.update(change["$set"])
        result = dict(current)
        current["state"] = "completing"
        return result

    env.collection.find_one_and_update.side_effect = update
    await direct.cancel_upload("ticket", env.user)
    assert current.get("cancel_requested") is True


@pytest.mark.asyncio
async def test_completion_admission_excludes_a_canceled_ticket(env):
    env.collection.find_one_and_update.return_value = None
    with pytest.raises(AppError):
        await direct.complete_upload("ticket", request(), env.user)
    query = env.collection.find_one_and_update.call_args.args[0]
    assert query["cancel_requested"] == {"$ne": True}


@pytest.mark.asyncio
async def test_cleanup_keeps_a_record_committed_before_a_worker_crash(env):
    env.records.find_by_key.return_value = {"key": env.ticket["key"]}
    await direct.cleanup_ticket(env.ticket, env.storage)
    env.storage.delete_file.assert_not_awaited()
    env.records.schedule_owned_cleanup.assert_awaited_once()


@pytest.mark.asyncio
async def test_expired_ticket_cleanup_is_claimed_atomically(env):
    env.collection.find_one_and_update.side_effect = [env.ticket, None]
    await direct.cleanup_expired_uploads()
    env.adapter.abort.assert_awaited_once()
    query = env.collection.find_one_and_update.call_args_list[0].args[0]
    assert "expires_at" in query and query["storage"] == env.ticket["storage"]
