"""Resume-safe file-cover backfill. Dry-run unless --apply; one file at a time."""

import argparse
import asyncio
import json
import re

from src.api.routes.upload_content_cover import CONTENT_COVER_EXTENSIONS
from src.api.routes.upload_cover import get_file_cover_response
from src.infra.revealed_file.storage import get_revealed_file_storage
from src.infra.storage.s3.media_cover import AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from src.infra.storage.s3.service import get_or_init_storage
from src.infra.upload.file_record import get_file_record_storage


async def main(apply: bool, limit: int) -> None:
    storage = await get_or_init_storage()
    extensions = (
        CONTENT_COVER_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | {"pdf", "xlsx", "xlsm"}
    )
    pattern = r"\.(" + "|".join(re.escape(ext) for ext in sorted(extensions)) + r")$"
    seen: set[str] = set()
    counts = dict(scanned=0, existing=0, created=0, unavailable=0)
    for collection, field in [
        (get_file_record_storage().collection, "key"),
        (get_revealed_file_storage().collection, "file_key"),
    ]:
        async for row in collection.find(
            {field: {"$regex": pattern, "$options": "i"}},
            {field: 1},
        ):
            key = row[field]
            if key in seen or "://" in key:
                continue
            seen.add(key)
            if limit and counts["scanned"] >= limit:
                break
            counts["scanned"] += 1
            cover = f"covers/560x315/{key}.jpg"
            if await storage.file_exists(cover):
                counts["existing"] += 1
            elif apply:
                try:
                    await get_file_cover_response(storage, key, None)
                    ready = await storage.file_exists(cover)
                except Exception:
                    ready = False
                counts["created" if ready else "unavailable"] += 1
            print(json.dumps({"key": key, **counts}), flush=True)
    print(json.dumps({"apply": apply, **counts}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    asyncio.run(main(args.apply, args.limit))
