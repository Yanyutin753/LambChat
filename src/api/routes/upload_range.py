"""Stream authorized object-storage byte ranges without exposing signed URLs."""

from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any

import anyio
import httpx
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask
from starlette.types import Receive, Scope, Send

from src.kernel.errors import AppError, ErrorCode


class _ClosingStreamingResponse(StreamingResponse):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # A disconnect before body iteration skips Starlette's background task.
            if self.background is not None:
                await self.background()


class _RejectCookies(DefaultCookiePolicy):
    def set_ok(self, cookie: Any, request: Any) -> bool:
        return False


def create_range_client() -> httpx.AsyncClient:
    # A dedicated pool must never carry storage cookies between users' objects.
    return httpx.AsyncClient(
        timeout=httpx.Timeout(30, read=120),
        follow_redirects=False,
        trust_env=False,
        cookies=CookieJar(policy=_RejectCookies()),
    )


async def get_private_range_response(
    storage: Any, key: str, range_header: str, *, client: httpx.AsyncClient
) -> Response:
    """The caller must authorize the file before opening this single upstream GET."""
    try:
        url = await storage.get_presigned_url(key, 60)
    except Exception:
        raise AppError(ErrorCode.FILE_URL_FAILED) from None
    upstream = None

    async def close() -> None:
        with anyio.CancelScope(shield=True):
            if upstream is not None:
                await upstream.aclose()

    try:
        upstream = await client.send(
            client.build_request(
                "GET", url, headers={"Range": range_header, "Accept-Encoding": "identity"}
            ),
            stream=True,
        )
        if upstream.status_code == 404:
            raise AppError(ErrorCode.FILE_NOT_FOUND)
        if upstream.status_code not in (200, 206, 416):
            raise AppError(ErrorCode.FILE_READ_FAILED)
        headers = {
            name: upstream.headers[name]
            for name in ("content-type", "content-length", "content-range", "accept-ranges")
            if name in upstream.headers
        }
        headers.update({"Cache-Control": "private, no-store", "Vary": "Authorization"})
        if upstream.status_code == 416:
            headers.pop("content-length", None)
            await close()
            return Response(status_code=416, headers=headers)
        if upstream.headers.get("content-encoding", "identity").lower() != "identity":
            raise AppError(ErrorCode.FILE_READ_FAILED)
        source = upstream

        async def chunks():
            try:
                async for chunk in source.aiter_raw(chunk_size=64 * 1024):
                    yield chunk
            finally:
                await close()

        return _ClosingStreamingResponse(
            chunks(),
            status_code=source.status_code,
            headers=headers,
            background=BackgroundTask(close),
        )
    except httpx.HTTPError:
        await close()
        raise AppError(ErrorCode.FILE_READ_FAILED) from None
    except BaseException:
        await close()
        raise
