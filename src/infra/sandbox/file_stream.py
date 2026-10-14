"""Bounded binary streams shared by workspace transports."""

from collections.abc import AsyncGenerator, AsyncIterator

from src.kernel.config import settings


def download_max_bytes() -> int:
    return max(1, int(getattr(settings, "S3_INTERNAL_UPLOAD_MAX_SIZE", 0) or 0))


async def bounded_async_chunks(
    chunks: AsyncIterator[bytes], expected_size: int | None = None
) -> AsyncGenerator[bytes, None]:
    limit = download_max_bytes()
    try:
        if expected_size is not None and expected_size > limit:
            raise ValueError("file_too_large")
        total = 0
        async for chunk in chunks:
            total += len(chunk)
            if total > limit:
                raise ValueError("file_too_large")
            yield chunk
        if expected_size is not None and total != expected_size:
            raise IOError("binary stream size mismatch")
    finally:
        close = getattr(chunks, "aclose", None)
        if close:
            await close()
