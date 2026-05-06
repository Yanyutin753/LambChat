import json
from types import SimpleNamespace

import pytest

from src.infra.tool import reveal_project_tool


def test_reveal_project_tool_description_mentions_folder_reveal() -> None:
    description = reveal_project_tool.reveal_project.description
    project_path_description = reveal_project_tool.reveal_project.args["project_path"][
        "description"
    ]

    assert "文件夹" in description
    assert "非前端" in description
    assert "folder" in description
    assert "index.html 或 package.json" not in project_path_description
    assert "文件夹" in project_path_description


def test_subagent_workflow_allows_folder_reveal() -> None:
    from src.agents.core.subagent_prompts import WORKFLOW_SECTION

    assert "Project / Folder Reveal" in WORKFLOW_SECTION
    assert "ordinary folders with many files" in WORKFLOW_SECTION
    assert 'mode: "folder"' in WORKFLOW_SECTION


class _Runtime:
    def __init__(
        self,
        backend: object,
        *,
        user_id: str | None = "user-1",
        base_url: str = "https://app.example.com",
    ) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {
            "configurable": {
                "backend": backend,
                "context": context,
                "base_url": base_url,
            }
        }


class _FakeStorage:
    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str]] = []

    async def upload_bytes(self, data: bytes, folder: str, filename: str, content_type: str):
        self.uploads.append((filename, data, content_type))
        return SimpleNamespace(
            key=f"{folder}/{filename}",
            size=len(data),
            content_type=content_type,
        )

    async def list_files(self, prefix: str) -> list[str]:
        return []

    async def delete_file(self, key: str) -> None:
        return None


class _FakeRevealedFileStorage:
    async def upsert_by_name(self, **kwargs) -> None:
        return None


def _install_common_patches(
    monkeypatch: pytest.MonkeyPatch,
    *,
    files: list[str],
    contents: dict[str, bytes],
) -> _FakeStorage:
    fake_storage = _FakeStorage()

    async def _get_storage():
        return fake_storage

    async def _list_project_files(_backend: object, _project_path: str) -> list[str]:
        return files

    async def _download_file_from_backend(_backend: object, file_path: str) -> bytes | None:
        return contents.get(file_path)

    monkeypatch.setattr(reveal_project_tool, "_get_storage", _get_storage)
    monkeypatch.setattr(reveal_project_tool, "_list_project_files", _list_project_files)
    monkeypatch.setattr(
        reveal_project_tool,
        "_download_file_from_backend",
        _download_file_from_backend,
    )
    monkeypatch.setattr(
        reveal_project_tool,
        "get_revealed_file_storage",
        lambda: _FakeRevealedFileStorage(),
    )

    return fake_storage


@pytest.mark.asyncio
async def test_reveal_project_keeps_common_folder_text_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/demo-folder"
    files = [
        f"{project_path}/README.md",
        f"{project_path}/main.py",
        f"{project_path}/scripts/deploy.sh",
        f"{project_path}/config/app.yaml",
        f"{project_path}/data/sample.json",
    ]
    contents = {
        files[0]: b"# Demo\n",
        files[1]: b"print('hello')\n",
        files[2]: b"#!/bin/sh\necho deploy\n",
        files[3]: b"port: 8080\n",
        files[4]: b'{"ok": true}\n',
    }
    _install_common_patches(monkeypatch, files=files, contents=contents)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(object()),
        )
    )

    assert result["type"] == "project_reveal"
    assert "/README.md" in result["files"]
    assert "/main.py" in result["files"]
    assert "/scripts/deploy.sh" in result["files"]
    assert "/config/app.yaml" in result["files"]
    assert "/data/sample.json" in result["files"]


@pytest.mark.asyncio
async def test_reveal_project_returns_folder_mode_without_frontend_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/backend-service"
    files = [
        f"{project_path}/README.md",
        f"{project_path}/src/app.py",
        f"{project_path}/pyproject.toml",
    ]
    contents = {
        files[0]: b"# Backend Service\n",
        files[1]: b"print('service')\n",
        files[2]: b"[project]\nname='backend-service'\n",
    }
    _install_common_patches(monkeypatch, files=files, contents=contents)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(object()),
        )
    )

    assert result["mode"] == "folder"
    assert result["entry"] is None


@pytest.mark.asyncio
async def test_reveal_project_keeps_project_mode_for_frontend_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = "/workspace/site"
    files = [
        f"{project_path}/index.html",
        f"{project_path}/src/main.jsx",
        f"{project_path}/package.json",
    ]
    contents = {
        files[0]: b'<!doctype html><div id="root"></div>',
        files[1]: b"import React from 'react';\n",
        files[2]: b'{"dependencies":{"react":"^19.0.0"}}',
    }
    _install_common_patches(monkeypatch, files=files, contents=contents)

    result = json.loads(
        await reveal_project_tool.reveal_project.coroutine(
            project_path=project_path,
            runtime=_Runtime(object()),
        )
    )

    assert result["mode"] == "project"
    assert result["entry"] == "/src/main.jsx"
