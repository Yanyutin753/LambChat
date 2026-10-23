"""An active document may only delegate its server-associated companion assets."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.upload import shared_files

MAIN = "revealed_files/main.html"
ASSET = "revealed_files/image.png"
SECRET = "document/owner/secret.txt"


@pytest.fixture
def resources(monkeypatch):
    records = {}
    lookup = AsyncMock(side_effect=lambda key: records.get(key))
    monkeypatch.setattr(
        shared_files, "get_file_record_storage", lambda: SimpleNamespace(find_by_key=lookup)
    )
    monkeypatch.setattr(
        shared_files, "owned_file_keys", AsyncMock(side_effect=lambda keys, owner: keys)
    )
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: SimpleNamespace(collection=SimpleNamespace(find_one=AsyncMock(return_value=None))),
    )
    return records


async def render(key, text):
    async def stream(_):
        yield text.encode()

    return await shared_files.read_authorized_file_text(
        SimpleNamespace(download_stream=stream), key, "owner"
    )


async def test_uploaded_html_cannot_delegate_arbitrary_owner_files(resources):
    resources[MAIN] = {"key": MAIN, "uploaded_by": "owner"}
    html = f'<script src="/api/upload/file/{SECRET}"></script>'
    assert await render(MAIN, html) == html


async def test_generated_html_only_signs_server_recorded_companions(resources):
    resources[MAIN] = {
        "key": MAIN,
        "uploaded_by": "owner",
        "hash": "generated:" + MAIN,
        "resource_keys": [ASSET],
    }
    html = f'<img src="/api/upload/file/{ASSET}"><img src="/api/upload/file/{SECRET}">'
    result = await render(MAIN, html)
    assert f"{ASSET}?file_token=" in result
    assert f'{SECRET}">' in result
    assert "resolve_resources=true" in result


async def test_companion_css_can_resolve_siblings_only_through_its_recorded_parent(resources):
    resources[MAIN] = {
        "key": MAIN,
        "uploaded_by": "owner",
        "hash": "generated:" + MAIN,
        "resource_keys": [ASSET, "revealed_files/style.css"],
    }
    resources["revealed_files/style.css"] = {
        "key": "revealed_files/style.css",
        "uploaded_by": "owner",
        "hash": "generated:revealed_files/style.css",
        "resource_parent_key": MAIN,
    }
    assert f"{ASSET}?file_token=" in await render(
        "revealed_files/style.css", f'url("/api/upload/file/{ASSET}")'
    )


async def test_parent_link_cannot_authorize_a_nonmember(resources):
    resources[MAIN] = {
        "key": MAIN,
        "uploaded_by": "owner",
        "hash": "generated:" + MAIN,
        "resource_keys": [ASSET],
    }
    resources[SECRET] = {
        "key": SECRET,
        "uploaded_by": "owner",
        "hash": "generated:" + SECRET,
        "resource_parent_key": MAIN,
    }
    html = f'url("/api/upload/file/{ASSET}")'
    assert await render(SECRET, html) == html


async def test_project_resources_require_membership_in_the_server_manifest(resources, monkeypatch):
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "APP_BASE_URL", "https://chat.example")
    root = "revealed_projects/site_1234"
    page, asset = root + "/main.html", root + "/image.png"
    project = {
        "file_key": root,
        "user_id": "owner",
        "source": "reveal_project",
        "project_meta": {
            "files": [
                {"url": "https://chat.example/api/upload/file/" + page},
                {"url": "https://chat.example/api/upload/file/" + asset},
                {"url": "https://evil.example/api/upload/file/" + SECRET},
            ]
        },
    }
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: SimpleNamespace(
            collection=SimpleNamespace(find_one=AsyncMock(return_value=project))
        ),
    )
    html = f'<img src="/api/upload/file/{asset}"><img src="/api/upload/file/{SECRET}">'
    result = await render(page, html)
    assert f"{asset}?file_token=" in result and f'{SECRET}">' in result
    assert await render(root + "/unlisted.html", html) == html


async def test_deleted_or_foreign_resource_parent_never_delegates(resources):
    resources[MAIN] = {
        "key": MAIN,
        "uploaded_by": "other",
        "hash": "generated:" + MAIN,
        "resource_keys": [ASSET, SECRET],
    }
    resources[SECRET] = {
        "key": SECRET,
        "uploaded_by": "owner",
        "hash": "generated:" + SECRET,
        "resource_parent_key": MAIN,
    }
    html = f'url("/api/upload/file/{ASSET}")'
    assert await render(SECRET, html) == html
    resources[MAIN].update(uploaded_by="owner", deleting_at="now")
    assert await render(SECRET, html) == html
