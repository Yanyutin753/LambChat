"""Project file capabilities into explicit shares without changing stored events."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from html import escape, unescape
from typing import Any

from src.infra.upload.access import file_access_url, upload_key_from_url, validate_file_key
from src.infra.upload.file_record import get_file_record_storage
from src.kernel.errors import AppError, ErrorCode

TEXT_PREVIEW_MAX_BYTES = 8 * 1024 * 1024

_FILE_URL = re.compile(
    r"""(?:https?:)?//[^\s<>"')\]}]+|(?<![^\s<>"'(\[{=])/api/upload/file/[^\s<>"'\\)\]}]+"""
)
_HTML = re.compile(r"<\s*(?:!--|!doctype\b|/?[a-z][\w:-]*(?:\s[^<>]*|/?)>)", re.I)
_ACTIVE_TYPES = {"html", "code", "javascript", "js", "typescript", "ts", "jsx", "tsx", "css", "svg"}
_ACTIVE_MIME_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "text/javascript",
    "application/javascript",
    "text/css",
    "image/svg+xml",
}


def _map_project_manifest(value: dict, transform: Callable[[str], str]) -> dict:
    """Only project companions may receive capabilities inside an executable preview."""
    files = value.get("files")
    if value.get("version") == 2 and isinstance(files, dict):
        entries = list(files.items())
    elif value.get("version") == 3 and isinstance(files, list):
        entries = list(enumerate(files))
    else:
        return value

    roots: dict[Any, str | None] = {}
    paths: dict[Any, str | None] = {}
    for index, item in entries:
        root = None
        path = index if isinstance(index, str) else None
        if isinstance(item, dict):
            path = item.get("path", path)
            url = item.get("url")
            if isinstance(url, str) and _FILE_URL.fullmatch(url):
                try:
                    key = upload_key_from_url(url)
                except (AppError, ValueError):
                    key = None
                if key and key.startswith("revealed_projects/"):
                    parts = key.split("/", 2)
                    if len(parts) == 3:
                        root = "/".join(parts[:2]) + "/"
        roots[index] = root
        paths[index] = path if isinstance(path, str) else None

    entry = value.get("entry")
    if isinstance(entry, str) and entry:
        # Legacy Mongo event keys replace dots; entry remains the original path.
        candidates = {
            roots[index]
            for index, path in paths.items()
            if path == entry or value.get("version") == 2 and path == entry.replace(".", "_")
        }
    else:
        candidates = set(roots.values())
    if len(candidates) != 1 or None in candidates:
        return value
    root = next(iter(candidates))

    projected = {
        index: {**item, "url": transform(item["url"])}
        if roots[index] == root and isinstance(item, dict)
        else item
        for index, item in entries
    }
    return {
        **value,
        "files": projected if isinstance(files, dict) else list(projected.values()),
    }


def _map_file_urls(value: Any, transform: Callable[[str], str], *, skip_active: bool) -> Any:
    """Use identical traversal boundaries when collecting and replacing capabilities."""
    if isinstance(value, dict):
        if skip_active:
            kind = str(value.get("type", "")).lower()
            language = str(value.get("language", "")).lower()
            mime = str(value.get("content_type", value.get("mime_type", ""))).lower()
            if kind in _ACTIVE_TYPES or (
                any(field in value for field in ("content", "code", "files"))
                and (language in _ACTIVE_TYPES or mime in _ACTIVE_MIME_TYPES)
            ):
                return value
            if kind == "project_reveal":
                return _map_project_manifest(value, transform)
        return {
            key: _map_file_urls(child, transform, skip_active=skip_active)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_map_file_urls(child, transform, skip_active=skip_active) for child in value]
    if isinstance(value, str):
        if skip_active:
            if value.lstrip().startswith(("{", "[", '"')):
                try:
                    decoded = json.loads(value)
                except (ValueError, RecursionError):
                    pass
                else:
                    if isinstance(decoded, (dict, list, str)):
                        projected = _map_file_urls(decoded, transform, skip_active=True)
                        return (
                            value
                            if projected == decoded
                            else json.dumps(projected, ensure_ascii=False)
                        )
            if _HTML.search(value):
                return value
        return transform(value)
    return value


async def owned_file_keys(keys: set[str], owner_id: str) -> set[str]:
    if not keys:
        return set()
    for key in keys:
        validate_file_key(key)
    records = get_file_record_storage()
    existing = {
        doc["key"]: doc async for doc in records.collection.find({"key": {"$in": list(keys)}})
    }
    owned = {
        key
        for key, doc in existing.items()
        if doc.get("uploaded_by") == owner_id
        and not doc.get("deleting_at")
        and not doc.get("private_session_id")
        and not key.startswith("cua_screenshots/")
    }
    # Never let an old index override a current owner, deletion or capture boundary.
    missing = keys - existing.keys()
    if missing:
        from src.infra.revealed_file.storage import get_revealed_file_storage
        from src.infra.upload.generated_ownership import indexed_files
        from src.kernel.config import settings

        parents = {
            key.rsplit("/", depth)[0] for key in missing for depth in range(1, key.count("/") + 1)
        }
        async for doc in get_revealed_file_storage().collection.find(
            {"user_id": owner_id, "file_key": {"$in": list(missing | parents)}}
        ):
            owned.update(
                key for key, _ in indexed_files(doc, settings.APP_BASE_URL) if key in missing
            )
    return owned


async def authorize_shared_files(value: Any, share) -> Any:
    return await authorize_owned_files(value, share.owner_id, share=share, skip_active=True)


async def authorize_owned_files(
    value: Any,
    owner_id: str,
    *,
    share=None,
    resolve_resources=False,
    allowed_keys: set[str] | None = None,
    skip_active: bool = False,
    xml_urls: bool = False,
) -> Any:
    urls: dict[str, str] = {}

    def collect(text: str) -> str:
        for match in _FILE_URL.finditer(text):
            url = match.group()
            try:
                key = upload_key_from_url(unescape(url) if xml_urls else url)
            except AppError:
                continue
            if key and (allowed_keys is None or key in allowed_keys):
                urls[url] = key
        return text

    _map_file_urls(value, collect, skip_active=skip_active)
    owned = await owned_file_keys(set(urls.values()), owner_id)
    replacements = {}
    for url, key in urls.items():
        if key in owned:
            url_to_sign = unescape(url) if xml_urls else url
            signed = file_access_url(url_to_sign, key, share=share)
            if resolve_resources:
                from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

                parsed = urlsplit(signed)
                query = dict(parse_qsl(parsed.query))
                query["resolve_resources"] = "true"
                signed = urlunsplit(parsed._replace(query=urlencode(query)))
            if xml_urls:
                signed = escape(signed, quote=True)
            replacements[url] = signed

    def project(text: str) -> str:
        return _FILE_URL.sub(lambda match: replacements.get(match.group(), match.group()), text)

    return _map_file_urls(value, project, skip_active=skip_active)


async def read_authorized_file_text(
    storage, key: str, owner_id: str, *, share=None, xml_urls: bool = False
) -> str:
    content = bytearray()
    async for chunk in storage.download_stream(key):
        if len(content) + len(chunk) > TEXT_PREVIEW_MAX_BYTES:
            raise AppError(
                ErrorCode.FILE_TOO_LARGE, args={"max": TEXT_PREVIEW_MAX_BYTES // 1024 // 1024}
            )
        content.extend(chunk)
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise AppError(ErrorCode.FILE_READ_FAILED) from None
    allowed = await related_file_keys(key, owner_id)
    return await authorize_owned_files(
        text,
        owner_id,
        share=share,
        resolve_resources=True,
        allowed_keys=allowed,
        xml_urls=xml_urls,
    )


async def related_file_keys(key: str, owner_id: str) -> set[str]:
    """Only server-uploaded companions may gain capabilities inside active content."""
    from src.infra.revealed_file.storage import get_revealed_file_storage
    from src.infra.upload.generated_ownership import indexed_files
    from src.kernel.config import settings

    records = get_file_record_storage()
    record = await records.find_by_key(key)
    if record and (
        record.get("uploaded_by") != owner_id
        or record.get("deleting_at")
        or record.get("private_session_id")
    ):
        return set()
    if record and record.get("hash") == "generated:" + key:
        parent_key = record.get("resource_parent_key")
        if isinstance(parent_key, str):
            parent = await records.find_by_key(parent_key)
            if not parent or (
                parent.get("uploaded_by") != owner_id
                or parent.get("deleting_at")
                or parent.get("private_session_id")
                or parent.get("hash") != "generated:" + parent_key
                or key not in parent.get("resource_keys", [])
            ):
                return set()
            record = parent
        children = record.get("resource_keys", [])
        if isinstance(children, list) and children:
            return {child for child in children if isinstance(child, str)}
    if key.startswith("revealed_projects/") and key.count("/") >= 2:
        root = "/".join(key.split("/", 2)[:2])
        project = await get_revealed_file_storage().collection.find_one(
            {"file_key": root, "user_id": owner_id, "source": "reveal_project"}
        )
        if project and project.get("user_id") == owner_id:
            members = {child for child, _ in indexed_files(project, settings.APP_BASE_URL)}
            if key in members:
                return members
    return set()
