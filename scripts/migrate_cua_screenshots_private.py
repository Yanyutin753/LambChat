"""Register attributable legacy CUA captures as private; default is a metadata-only dry run."""

from __future__ import annotations

import argparse
import asyncio
import mimetypes
import uuid
from urllib.parse import unquote, urlsplit


def legacy_capture_keys(events: list[dict]) -> set[str]:
    keys = set()
    for event in events:
        data = event.get("data") or {}
        if event.get("event_type") != "tool:result" or data.get("tool") != "computer_use":
            continue
        result = data.get("result")
        screenshot = result.get("screenshot") if isinstance(result, dict) else None
        url = screenshot.get("url") if isinstance(screenshot, dict) else None
        if not isinstance(url, str):
            continue
        parsed = urlsplit(url)
        prefix = "/api/upload/file/tool_binaries/"
        path = unquote(parsed.path)
        if parsed.netloc or parsed.scheme or not path.startswith(prefix):
            continue
        key = path.removeprefix("/api/upload/file/")
        if "\\" not in key and all(part not in ("", ".", "..") for part in key.split("/")):
            keys.add(key)
    return keys


async def migrate(*, apply: bool) -> dict[str, int | bool]:
    from src.infra.session.storage import SessionStorage
    from src.infra.session.trace_storage import get_trace_storage
    from src.infra.storage.s3.service import get_or_init_storage
    from src.infra.upload.file_record import FileRecordStorage
    from src.infra.utils.datetime import utc_now

    if apply:
        storage = await get_or_init_storage()
        if not storage.is_local and storage._config.public_bucket:
            raise RuntimeError("Make the storage bucket private before migrating desktop captures")
    traces = get_trace_storage()
    sessions = SessionStorage()
    files = FileRecordStorage()
    if apply:
        await files.initialize_indexes()
    counts = {"apply": apply, "captures": 0, "registered": 0, "unattributed": 0}
    seen = set()
    attributed: dict[str, tuple[str | None, str | None]] = {}
    projection = {
        "session_id": 1,
        "events.event_type": 1,
        "events.data.tool": 1,
        "events.data.result.screenshot.url": 1,
    }
    for collection in (traces.collection, traces.chunks_collection):
        async for doc in collection.find({"events.data.tool": "computer_use"}, projection):
            session_id = doc.get("session_id")
            for key in legacy_capture_keys(doc.get("events") or []):
                pair = (key, session_id)
                if pair in seen:
                    continue
                seen.add(pair)
                counts["captures"] += 1
                session = (
                    await sessions.collection.find_one({"session_id": session_id}, {"user_id": 1})
                    if session_id
                    else None
                )
                owner = session.get("user_id") if session else None
                existing = await files.collection.find_one(
                    {"key": key}, {"uploaded_by": 1, "private_session_id": 1}
                )
                target_session_id = session_id
                conflict = (
                    (key in attributed and attributed[key] != (owner, session_id))
                    or existing
                    and (
                        existing.get("uploaded_by") != owner
                        or existing.get("private_session_id", session_id) != session_id
                    )
                )
                leased = False
                if apply and owner and not conflict:
                    leased = await sessions.acquire_trace_write(session_id)
                    if not leased:
                        conflict = True
                if not owner or conflict:
                    counts["unattributed"] += 1
                    owner = "__unattributed__"
                    target_session_id = "__unattributed__"
                attributed[key] = (owner, target_session_id)
                if not apply:
                    continue
                now = utc_now()
                # Conflicting or orphaned attribution is quarantined, never left public.
                try:
                    await files.collection.update_one(
                        {"key": key},
                        {
                            "$set": {
                                "uploaded_by": owner,
                                "private_session_id": target_session_id,
                                "reference_count": 1,
                                "updated_at": now,
                            },
                            "$setOnInsert": {
                                "hash": uuid.uuid4().hex,
                                "key": key,
                                "name": "screenshot.png",
                                "mime_type": mimetypes.guess_type(key)[0] or "image/png",
                                "size": 0,
                                "category": "image",
                                "created_at": now,
                            },
                        },
                        upsert=True,
                    )
                finally:
                    if leased:
                        await sessions.release_trace_write(session_id)
                counts["registered"] += 1
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist private records; without this flag, read metadata only",
    )
    print(asyncio.run(migrate(apply=parser.parse_args().apply)))
