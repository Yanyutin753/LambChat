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
from src.kernel.errors import AppError, ErrorCode


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
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1, matched_count=1)),
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
    assert result["first_part_url"] == "https://storage/part"
    env.adapter.sign_part.assert_awaited_once_with(doc["key"], "upload-id", 1, 3)
    with pytest.raises(AppError):
        await direct.start_upload(direct.StartUpload(name="a.txt", size=101), env.user)
    assert env.adapter.create.await_count == 1


async def test_initial_signature_failure_cleans_up_created_multipart(env):
    env.adapter.sign_part.side_effect = OSError("signing failed")
    with pytest.raises(OSError, match="signing failed"):
        await direct.start_upload(direct.StartUpload(name="a.txt", size=3), env.user)
    env.adapter.abort.assert_awaited_once()
    env.collection.delete_one.assert_awaited_once()


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
    assert any(
        call.args[1].get("$set", {}).get("verified_bytes") == 3
        for call in env.collection.update_one.call_args_list
    )


@pytest.mark.asyncio
async def test_status_reports_only_owned_verification_progress(env):
    env.ticket.update(state="completing", verified_bytes=1)
    assert await direct.upload_status("ticket", env.user) == {"state": "completing", "progress": 33}
    assert env.collection.find_one.call_args.args[0] == {"_id": "ticket", "owner": "user"}
    env.ticket.pop("verified_bytes")
    assert (await direct.upload_status("ticket", env.user))["progress"] is None
    env.ticket.update(state="committing", verified_bytes=3)
    assert (await direct.upload_status("ticket", env.user))["progress"] == 99
    env.ticket["state"] = "completed"
    assert (await direct.upload_status("ticket", env.user))["progress"] == 100
    env.collection.find_one.return_value = None
    with pytest.raises(AppError):
        await direct.upload_status("ticket", env.user)


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
async def test_cancel_during_hashing_prevents_record_and_deletes_object(env, monkeypatch):
    verification_stream(env, monkeypatch, [b"a", b"bc"], times=[0.0, 0.3], cancel_at=1)
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


def verification_stream(env, monkeypatch, chunks, times=None, cancel_at=None, cancel_at_eof=False):
    """A stateful cross-replica ticket: conditional writes observe the same cancellation as reads."""
    payload = b"".join(chunks)
    env.ticket["size"] = len(payload)
    env.adapter.list_parts.return_value = [{"PartNumber": 1, "ETag": "etag", "Size": len(payload)}]
    env.storage.get_size.return_value = len(payload)
    env.records.create.return_value["size"] = len(payload)
    monkeypatch.setattr(
        upload,
        "validate_upload_metadata",
        AsyncMock(return_value=(FileCategory.DOCUMENT, len(payload))),
    )
    clock = SimpleNamespace(now=0.0, yielded=0)
    current = dict(env.ticket)
    monkeypatch.setattr(direct, "monotonic", lambda: clock.now, raising=False)

    def matches(query):
        for key in ("_id", "owner", "state"):
            if key in query and current.get(key) != query[key]:
                return False
        if query.get("cancel_requested") == {"$ne": True} and current.get("cancel_requested"):
            return False
        return True

    async def find_one(query, *args):
        return dict(current) if matches(query) else None

    async def claim(query, change, **kwargs):
        if not matches({key: value for key, value in query.items() if key != "expires_at"}):
            return None
        current.update(change["$set"])
        return dict(current)

    async def update(query, change):
        matched = matches(query)
        if matched:
            current.update(change["$set"])
        return SimpleNamespace(matched_count=int(matched), modified_count=int(matched))

    async def stream(key):
        for index, chunk in enumerate(chunks):
            clock.now = times[index] if times else 0.0
            if index == cancel_at:
                current["cancel_requested"] = True
            clock.yielded += 1
            yield chunk
        if cancel_at_eof:
            current["cancel_requested"] = True

    env.collection.find_one.side_effect = find_one
    env.collection.find_one_and_update.side_effect = claim
    env.collection.update_one.side_effect = update
    env.storage.download_stream = stream
    return current, clock, payload


@pytest.mark.asyncio
@pytest.mark.parametrize("chunk_count", [1, 1000])
async def test_verification_database_work_is_independent_of_fast_stream_chunk_count(
    env, monkeypatch, chunk_count
):
    chunks = [b"x" * (1000 // chunk_count)] * chunk_count
    current, clock, payload = verification_stream(env, monkeypatch, chunks)
    result = await direct.complete_upload("ticket", request(), env.user)
    assert result["key"] == current["key"]
    assert clock.yielded == chunk_count
    assert env.records.create.call_args.kwargs["file_hash"] == hashlib.sha256(payload).hexdigest()
    assert env.records.create.call_args.kwargs["size"] == len(payload)
    assert (
        env.collection.find_one.await_count == 1
    )  # ownership read only; progress uses atomic writes
    assert (
        env.collection.update_one.await_count <= 4
    )  # initial/final progress plus two commit transitions
    samples = [
        call
        for call in env.collection.update_one.call_args_list
        if "verified_bytes" in call.args[1].get("$set", {})
    ]
    assert samples[0].args[1]["$set"]["verified_bytes"] == 0
    assert samples[-1].args[1]["$set"]["verified_bytes"] == len(payload)
    for sample in samples:
        assert sample.args[0]["owner"] == env.user.sub
        assert sample.args[0]["state"] == "completing"
        assert sample.args[0]["cancel_requested"] == {"$ne": True}
        assert sample.args[1]["$set"]["expires_at"] > utc_now() + timedelta(minutes=59)
    assert current["state"] == "completed"


@pytest.mark.asyncio
async def test_verification_checkpoints_use_elapsed_time_and_publish_final_progress(
    env, monkeypatch
):
    verification_stream(env, monkeypatch, [b"a"] * 6, times=[0.0, 0.1, 0.249, 0.25, 0.4, 0.5])
    await direct.complete_upload("ticket", request(), env.user)
    progress = [
        call.args[1]["$set"]["verified_bytes"]
        for call in env.collection.update_one.call_args_list
        if "verified_bytes" in call.args[1].get("$set", {})
    ]
    assert progress[0] == 0 and progress[-1] == 6
    assert 4 in progress  # first interval has elapsed, even though the object is still streaming
    assert len(progress) <= 4
    assert progress == sorted(progress)
    assert env.collection.find_one.await_count == 1


@pytest.mark.asyncio
async def test_verification_cancellation_is_observed_at_the_next_bounded_checkpoint(
    env, monkeypatch
):
    current, clock, _ = verification_stream(
        env, monkeypatch, [b"a"] * 10, times=[index / 10 for index in range(10)], cancel_at=1
    )
    with pytest.raises(AppError) as error:
        await direct.complete_upload("ticket", request(), env.user)
    assert error.value.error_code == ErrorCode.UPLOAD_CANCELED
    assert 2 <= clock.yielded <= 4  # cancel after 100ms is observed by the first >=250ms chunk
    env.records.create.assert_not_awaited()
    env.storage.delete_file.assert_awaited_once_with(env.ticket["key"])
    assert current["state"] == "cleanup"
    assert env.collection.find_one.await_count == 1


@pytest.mark.asyncio
async def test_cancel_after_last_chunk_still_wins_before_record_commit(env, monkeypatch):
    current, _, _ = verification_stream(env, monkeypatch, [b"a"] * 10, cancel_at_eof=True)
    with pytest.raises(AppError) as error:
        await direct.complete_upload("ticket", request(), env.user)
    assert error.value.error_code == ErrorCode.UPLOAD_CANCELED
    env.records.create.assert_not_awaited()
    assert current["state"] == "cleanup"
    env.storage.delete_file.assert_awaited_once_with(env.ticket["key"])


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["short", "oversized"])
async def test_verification_still_rejects_stream_size_mismatch_before_record(
    env, monkeypatch, mismatch
):
    _, _, _ = verification_stream(env, monkeypatch, [b"abc"])

    async def stream(key):
        yield b"ab" if mismatch == "short" else b"abcd"

    env.storage.download_stream = stream
    with pytest.raises(AppError):
        await direct.complete_upload("ticket", request(), env.user)
    env.records.create.assert_not_awaited()
    env.storage.delete_file.assert_awaited_once_with(env.ticket["key"])


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["start", "complete", "redirect", "proxy"])
async def test_upload_phase_headers_are_bounded_and_never_include_ticket_or_file_data(
    env, monkeypatch, route
):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from src.api.middleware.tracing import TracingMiddleware

    app = FastAPI()
    app.add_middleware(TracingMiddleware)
    app.include_router(direct.router, prefix="/api/upload")
    app.add_api_route("/api/upload/file/{key:path}", upload.get_file_proxy, methods=["GET"])
    app.add_api_route("/api/upload/file", upload.upload_file, methods=["POST"])
    app.dependency_overrides[direct.get_current_user_required] = lambda: env.user
    app.dependency_overrides[upload.get_current_user] = lambda: env.user
    if route == "complete":
        verification_stream(env, monkeypatch, [b"abc"])
    if route == "proxy":
        monkeypatch.setattr(
            upload,
            "validate_upload_metadata",
            AsyncMock(return_value=(FileCategory.DOCUMENT, 10000)),
        )
        env.storage.upload_stream_to_key = AsyncMock(
            return_value=SimpleNamespace(key=env.ticket["key"])
        )
    if route == "redirect":
        env.records.is_private_key = AsyncMock(return_value=False)
        env.records.find_by_key = AsyncMock(return_value={"uploaded_by": env.user.sub})
        monkeypatch.setattr("src.infra.upload.access.get_file_record_storage", lambda: env.records)
        env.storage._config = SimpleNamespace(public_bucket=False)
        env.storage.get_presigned_url = AsyncMock(
            return_value="https://storage.example/private?secret=1"
        )
        monkeypatch.setattr(upload, "get_model_safe_file_response", AsyncMock(return_value=None))
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="https://app.example"
    ) as client:
        if route == "start":
            response = await client.post(
                "/api/upload/direct", json={"name": "private-name.txt", "size": 3}
            )
        elif route == "complete":
            response = await client.post("/api/upload/direct/ticket/complete")
        elif route == "proxy":
            response = await client.post(
                "/api/upload/file", files={"file": ("private-name.txt", b"abc", "text/plain")}
            )
        else:
            response = await client.get("/api/upload/file/document/user/private-name.txt")
    assert response.status_code == (302 if route == "redirect" else 200)
    timing = response.headers.get("Server-Timing", "")
    names = {metric.split(";", 1)[0].strip() for metric in timing.split(",") if metric}
    assert "upload_storage" in names
    assert names == (
        {"upload_storage", "upload_verify"}
        if route in ("complete", "proxy")
        else {"upload_storage"}
    )
    assert all(";dur=" in metric for metric in timing.split(","))
    for private in ("ticket", "user", "private-name", "secret", "storage.example"):
        assert private not in timing
    if route == "redirect":
        env.storage.file_exists.assert_awaited_once_with("document/user/private-name.txt")
