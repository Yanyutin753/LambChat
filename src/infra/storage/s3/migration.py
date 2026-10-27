"""Streaming, exhaustive verification before a storage location can change."""

import hashlib


async def _digest(backend, key: str) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    async for chunk in backend.download_stream(key):
        digest.update(chunk)
        size += len(chunk)
    return size, digest.hexdigest()


async def verify_contents(source, destination, required: dict[str, str | None]) -> dict[str, int]:
    """Check original bytes, including objects without a file-record entry."""
    source_keys = {key async for key in source.iter_keys()}
    destination_keys = {key async for key in destination.iter_keys()}
    keys = source_keys | required.keys()
    missing = keys - destination_keys
    if missing:
        raise ValueError(f"Storage migration incomplete: {len(missing)} missing objects")
    size = 0
    for key in sorted(keys):
        actual = await _digest(destination, key)
        if key in source_keys:
            expected = await _digest(source, key)
            if actual != expected:
                raise ValueError("Storage migration checksum mismatch")
        elif required[key] is None:
            raise ValueError("Storage migration source is missing and has no verified checksum")
        elif actual[1] != required[key]:
            raise ValueError("Storage migration checksum mismatch")
        if required.get(key) and actual[1] != required[key]:
            raise ValueError("Storage migration checksum mismatch with original record")
        size += actual[0]
    return {"objects": len(keys), "bytes": size}
