import pytest

from src.infra.sandbox.file_stream import bounded_async_chunks
from src.kernel.config import settings


async def test_stream_is_lazy_and_closes_source_on_cancel(monkeypatch):
    monkeypatch.setattr(settings, "S3_INTERNAL_UPLOAD_MAX_SIZE", 6)
    closed = []

    async def source():
        try:
            yield b"abc"
            raise AssertionError("must not prefetch whole file")
        finally:
            closed.append(True)

    result = bounded_async_chunks(source(), 6)
    assert await anext(result) == b"abc"
    await result.aclose()
    assert closed == [True]


async def test_stream_obeys_limit_including_unknown_size_and_changed_limit(monkeypatch):
    async def source():
        yield b"abc"
        yield b"d"

    monkeypatch.setattr(settings, "S3_INTERNAL_UPLOAD_MAX_SIZE", 3)
    with pytest.raises(ValueError, match="file_too_large"):
        [chunk async for chunk in bounded_async_chunks(source(), 4)]
    with pytest.raises(ValueError, match="file_too_large"):
        [chunk async for chunk in bounded_async_chunks(source())]
    monkeypatch.setattr(settings, "S3_INTERNAL_UPLOAD_MAX_SIZE", 4)
    assert b"".join([chunk async for chunk in bounded_async_chunks(source(), 4)]) == b"abcd"


async def test_stream_rejects_truncation():
    async def source():
        yield b"abc"

    with pytest.raises(IOError, match="size mismatch"):
        [chunk async for chunk in bounded_async_chunks(source(), 4)]
