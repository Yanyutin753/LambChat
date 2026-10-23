"""XML document previews resolve only explicitly associated private resources."""

import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest

from src.api.routes.upload_preview import get_text_preview_response
from src.infra.upload import access, shared_files

CHILD = "revealed_files/linked.png"
UNRELATED = "image/owner/unrelated.png"


@pytest.mark.parametrize(
    "mime,filename,content",
    [
        (
            "image/svg+xml",
            "drawing.svg",
            (
                '<svg xmlns="http://www.w3.org/2000/svg">'
                f'<image href="/api/upload/file/{CHILD}?quality=full&amp;download=1"/>'
                f'<image href="/api/upload/file/{UNRELATED}"/></svg>'
            ),
        ),
        (
            "application/xhtml+xml",
            "page.xhtml",
            (
                '<html xmlns="http://www.w3.org/1999/xhtml"><body>'
                f'<img src="/api/upload/file/{CHILD}?quality=full&amp;download=1"/>'
                f'<img src="/api/upload/file/{UNRELATED}"/></body></html>'
            ),
        ),
    ],
)
async def test_xml_previews_resolve_recorded_companions_without_signing_unrelated_owner_files(
    monkeypatch, mime, filename, content
):
    key = "revealed_files/" + filename
    documents = {
        item: {"key": item, "uploaded_by": "owner", "hash": "generated:" + item}
        for item in [key, CHILD, UNRELATED]
    }
    documents[key].update(name=filename, mime_type=mime, resource_keys=[CHILD])

    async def rows(query):
        for item in query["key"]["$in"]:
            if item in documents:
                yield documents[item]

    records = SimpleNamespace(
        is_private_key=AsyncMock(return_value=False),
        find_by_key=AsyncMock(side_effect=lambda item, *args: documents.get(item)),
        collection=SimpleNamespace(find=rows),
    )
    monkeypatch.setattr(access, "get_file_record_storage", lambda: records)
    monkeypatch.setattr(shared_files, "get_file_record_storage", lambda: records)

    async def stream(item):
        assert item == key
        yield content.encode()

    response = await get_text_preview_response(
        SimpleNamespace(download_stream=stream), key, records
    )
    assert response is not None
    assert response.status_code == 200
    assert response.media_type == mime
    assert response.headers["cache-control"] == "private, no-store"
    document = ET.fromstring(response.body)
    urls = [node.attrib.get("href", node.attrib.get("src")) for node in document.iter()]
    urls = [url for url in urls if url]
    linked = next(url for url in urls if CHILD in url)
    unrelated = next(url for url in urls if UNRELATED in url)
    query = parse_qs(urlsplit(linked).query)
    assert query["quality"] == ["full"]
    assert query["download"] == ["1"]
    assert query["resolve_resources"] == ["true"]
    token = query["file_token"][0]
    await access.require_file_access(CHILD, None, token=token)
    assert unrelated == "/api/upload/file/" + UNRELATED
