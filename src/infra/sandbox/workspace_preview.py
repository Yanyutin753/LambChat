"""Provider-neutral workspace preview policy; transports retain their own size limits."""

import base64
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from src.infra.skill.binary import is_binary_file


async def read_workspace_preview(
    path: str,
    offset: int,
    limit: int,
    *,
    read: Callable[[str, int, int], Awaitable[dict[str, Any]]],
    download: Callable[[str], Awaitable[bytes | str]],
    stream: Callable[[str], AsyncIterator[bytes]] | None = None,
) -> dict[str, Any] | AsyncIterator[bytes]:
    if not is_binary_file(path):
        result = await read(path, offset, limit)
        error = str(result.get("error", ""))
        if not error.startswith(
            ("file too large to read directly:", "Binary file exceeds maximum preview size")
        ):
            return result
    # Skip lossy text reads for known binary files; use the bounded transfer channel.
    if stream is not None:
        return stream(path)
    content = await download(path)
    if isinstance(content, str):
        return {"error": content}
    return {"encoding": "base64", "content": base64.b64encode(content).decode("ascii")}
