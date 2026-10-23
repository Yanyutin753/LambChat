"""Authorized capture responses and text previews with owned resource links."""

from typing import Any

from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from src.api.routes.upload_cover import _path_exists
from src.api.routes.upload_thumb import get_private_file_thumb_response
from src.infra.async_utils import run_long_blocking_io
from src.kernel.errors import AppError, ErrorCode


async def get_file_response_metadata(key: str, records: Any) -> tuple[str | None, str]:
    record = await records.find_by_key(key)
    filename_for_disposition = record["name"] if record else None
    content_type = record["mime_type"] if record and record.get("mime_type") else None

    if not content_type:
        import mimetypes

        content_type, _ = mimetypes.guess_type(key)
        if not content_type:
            content_type = "application/octet-stream"

    return filename_for_disposition, content_type


def inline_content_disposition(filename: str) -> str:
    """Encode non-ASCII filenames using RFC 5987 instead of invalid latin-1 headers."""
    from urllib.parse import quote

    quoted = quote(filename)
    if quoted != filename:
        return f"inline; filename*=utf-8''{quoted}"
    return f'inline; filename="{filename.replace(chr(34), "")}"'


def get_local_file_url_response(url: str, key: str, file_token: str | None) -> Response:
    """Preserve the already-authorized capability when resolving a local file URL."""
    from urllib.parse import urlencode

    from src.infra.upload.access import file_access_url

    target = (
        url + "?" + urlencode({"file_token": file_token})
        if file_token
        else file_access_url(url, key)
    )
    return JSONResponse({"url": target}, headers={"Cache-Control": "private, no-store"})


async def get_private_capture_response(
    storage: Any, key: str, record: dict, *, thumb: bool = False
) -> Response:
    """The caller must have authorized this capture's owner and session first."""
    headers = {"Cache-Control": "private, no-store", "Vary": "Authorization"}
    if not storage.is_local and storage._config.public_bucket:
        raise AppError(ErrorCode.FILE_NOT_FOUND)
    if thumb:
        return await get_private_file_thumb_response(storage, key)
    if storage.is_local:
        path = storage.get_file_path(key)
        if not await run_long_blocking_io(_path_exists, path):
            raise AppError(ErrorCode.FILE_NOT_FOUND)
        return FileResponse(path=str(path), media_type=record["mime_type"], headers=headers)
    return StreamingResponse(
        storage.download_stream(key), media_type=record["mime_type"], headers=headers
    )


async def get_text_preview_response(
    storage: Any, key: str, records: Any, *, share=None
) -> Response | None:
    """The caller must authorize the primary file before resolving its resources."""
    _, content_type = await get_file_response_metadata(key, records)
    base_type = content_type.split(";", 1)[0]
    xml_urls = base_type in {"image/svg+xml", "application/xhtml+xml"}
    if not xml_urls and base_type not in {
        "text/html",
        "text/markdown",
        "text/css",
        "text/javascript",
        "application/javascript",
    }:
        return None
    record = await records.find_by_key(key)
    owner_id = record.get("uploaded_by") if record else None
    if not owner_id:
        from src.infra.revealed_file.storage import get_revealed_file_storage

        revealed_storage = get_revealed_file_storage()
        revealed = await revealed_storage.collection.find_one({"file_key": key})
        if not revealed and key.startswith("revealed_projects/") and key.count("/") >= 2:
            root = "/".join(key.split("/", 2)[:2])
            revealed = await revealed_storage.collection.find_one(
                {"file_key": root, "source": "reveal_project"}
            )
        owner_id = revealed.get("user_id") if revealed else None
    if not owner_id:
        return None
    from src.infra.upload.shared_files import read_authorized_file_text

    content = await read_authorized_file_text(
        storage, key, owner_id, share=share, xml_urls=xml_urls
    )
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "private, no-store", "Vary": "Authorization"},
    )
