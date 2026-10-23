"""Sharing text must not grant file capabilities to embedded executable content."""

import copy
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.infra.upload import shared_files

KEY = "image/owner/private.png"
URL = f"/api/upload/file/{KEY}"
SCRIPT = f'const privateUrl = "{URL}"; fetch(privateUrl);'
HTML = f'<script>{SCRIPT}</script><img src="{URL}">'


@pytest.fixture
def sharing(monkeypatch):
    monkeypatch.setattr("src.kernel.config.settings.APP_BASE_URL", "https://chat.example")
    owned = AsyncMock(side_effect=lambda keys, owner: keys & {KEY})
    mint = Mock(wraps=shared_files.file_access_url)
    monkeypatch.setattr(shared_files, "owned_file_keys", owned)
    monkeypatch.setattr(shared_files, "file_access_url", mint)
    share = SimpleNamespace(
        owner_id="owner", share_id="share", updated_at=datetime.now(timezone.utc)
    )
    return share, mint


@pytest.mark.parametrize("html", [HTML, f'<img src="{URL}">', f"<SCRIPT>{SCRIPT}</SCRIPT>"])
async def test_inline_html_does_not_mint_owner_file_capabilities(sharing, html):
    share, mint = sharing

    projected = await shared_files.authorize_shared_files(html, share)

    assert projected == html
    mint.assert_not_called()


async def test_serialized_tool_json_preserves_html_without_minting_capabilities(sharing):
    share, mint = sharing
    payload = {"type": "html", "content": HTML}

    projected = await shared_files.authorize_shared_files(json.dumps(payload), share)

    assert isinstance(projected, str)
    assert json.loads(projected) == payload
    mint.assert_not_called()


@pytest.mark.parametrize("serialized", [False, True])
@pytest.mark.parametrize("version", [None, 1])
async def test_project_reveal_v1_inline_files_never_receive_file_capabilities(
    sharing, serialized, version
):
    share, mint = sharing
    payload = {
        "type": "project_reveal",
        "name": "legacy inline project",
        "template": "vanilla",
        "files": {"/index.html": HTML, "/index.js": SCRIPT},
    }
    if version is not None:
        payload["version"] = version
    original = copy.deepcopy(payload)
    value = json.dumps(payload) if serialized else payload

    projected = await shared_files.authorize_shared_files(value, share)

    assert (json.loads(projected) if serialized else projected) == original
    assert payload == original
    mint.assert_not_called()


async def test_typed_javascript_content_does_not_mint_file_capabilities(sharing):
    share, mint = sharing
    payload = {"type": "code", "language": "javascript", "content": SCRIPT}

    projected = await shared_files.authorize_shared_files(payload, share)

    assert projected == payload
    mint.assert_not_called()


@pytest.mark.parametrize("serialized", [False, True])
async def test_attachment_and_markdown_still_sign_without_rewriting_active_siblings(
    sharing, serialized
):
    share, mint = sharing
    payload = {
        "attachments": [{"type": "image", "url": URL}],
        "text": f"![private photo]({URL}?thumb=1)",
        "tool_result": {"type": "html", "content": HTML},
        "project": {
            "type": "project_reveal",
            "version": 1,
            "name": "inline",
            "template": "vanilla",
            "files": {"/index.js": SCRIPT},
        },
    }
    original = copy.deepcopy(payload)

    projected = await shared_files.authorize_shared_files(
        json.dumps(payload) if serialized else payload, share
    )
    if serialized:
        assert isinstance(projected, str)
        projected = json.loads(projected)

    assert "file_token=" in projected["attachments"][0]["url"]
    assert "file_token=" in projected["text"]
    assert "thumb=1" in projected["text"]
    assert projected["tool_result"] == original["tool_result"]
    assert projected["project"] == original["project"]
    assert payload == original
    assert mint.call_count == 2


@pytest.mark.parametrize("version", [2, 3])
@pytest.mark.parametrize("serialized", [False, True])
async def test_project_manifest_only_signs_files_under_the_entry_project_root(
    sharing, monkeypatch, version, serialized
):
    share, _ = sharing
    monkeypatch.setattr(
        shared_files, "owned_file_keys", AsyncMock(side_effect=lambda keys, owner: keys)
    )
    manifest = [
        {"path": "/index.html", "url": "/api/upload/file/revealed_projects/site/index.html"},
        {"path": "/asset.png", "url": "/api/upload/file/revealed_projects/site/asset.png"},
        {"path": "/secret.png", "url": URL},
        {"path": "/other.js", "url": "/api/upload/file/revealed_projects/other/app.js"},
    ]
    project = {
        "type": "project_reveal",
        "version": version,
        "entry": "/index.html",
        "files": (
            {item["path"]: {"url": item["url"]} for item in manifest} if version == 2 else manifest
        ),
    }
    # The same arbitrary URL can be authorized as a standalone attachment, but
    # must not inherit that capability inside an executable project manifest.
    payload = {"project": project, "attachments": [{"url": URL}]}
    original = copy.deepcopy(payload)
    projected = await shared_files.authorize_shared_files(
        json.dumps(payload) if serialized else payload, share
    )
    if serialized:
        projected = json.loads(projected)
    files = projected["project"]["files"]
    entries = list(files.values()) if version == 2 else files

    assert "file_token=" in entries[0]["url"]
    assert "file_token=" in entries[1]["url"]
    assert entries[2]["url"] == URL
    assert entries[3]["url"] == manifest[3]["url"]
    assert "file_token=" in projected["attachments"][0]["url"]
    assert payload == original


@pytest.mark.parametrize("mixed", [False, True])
async def test_folder_manifest_without_entry_requires_one_server_project_root(
    sharing, monkeypatch, mixed
):
    share, mint = sharing
    monkeypatch.setattr(
        shared_files, "owned_file_keys", AsyncMock(side_effect=lambda keys, owner: keys)
    )
    project = {
        "type": "project_reveal",
        "version": 3,
        "mode": "folder",
        "files": [
            {"path": "/readme.txt", "url": "/api/upload/file/revealed_projects/site/readme.txt"},
            {
                "path": "/image.png",
                "url": URL if mixed else "/api/upload/file/revealed_projects/site/image.png",
            },
        ],
    }

    projected = await shared_files.authorize_shared_files(project, share)

    if mixed:
        assert projected == project
        mint.assert_not_called()
    else:
        assert all("file_token=" in item["url"] for item in projected["files"])
