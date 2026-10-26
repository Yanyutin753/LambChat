from types import SimpleNamespace
from unittest.mock import AsyncMock

from scripts import backfill_file_covers as backfill


async def test_backfill_is_dry_by_default_and_skips_duplicates_and_existing_covers(monkeypatch):
    objects = set()

    class Collection:
        def find(self, query, projection):
            field = next(iter(projection))

            async def rows():
                yield {field: "video/owner/clip.mp4"}
                yield {field: "video/owner/clip.mp4"}

            return rows()

    storage = SimpleNamespace(file_exists=AsyncMock(side_effect=lambda key: key in objects))
    monkeypatch.setattr(backfill, "get_or_init_storage", AsyncMock(return_value=storage))
    for name in ("get_file_record_storage", "get_revealed_file_storage"):
        monkeypatch.setattr(backfill, name, lambda: SimpleNamespace(collection=Collection()))

    async def render(storage, key, timestamp):
        objects.add(f"covers/560x315/{key}.jpg")

    render_mock = AsyncMock(side_effect=render)
    monkeypatch.setattr(backfill, "get_file_cover_response", render_mock)
    await backfill.main(False, 0)
    render_mock.assert_not_awaited()
    await backfill.main(True, 0)
    await backfill.main(True, 0)
    assert render_mock.await_count == 1
