from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.routes import skill as skill_route
from src.kernel.schemas.user import TokenPayload


def _fake_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["skill:read"],
    )


class _FakeUserDoc:
    metadata = {
        "disabled_skills": ["archived"],
        "pinned_skill_names": ["planner"],
        "favorite_skill_names": ["writer"],
    }


class _FakeUserStorage:
    async def get_by_id(self, user_id: str):
        assert user_id == "user-1"
        return _FakeUserDoc()


class _ChunkedUpload:
    def __init__(
        self,
        *,
        filename: str,
        data: bytes,
        chunk_size: int = 64 * 1024,
        content_type: str | None = None,
    ) -> None:
        self.filename = filename
        self.content_type = content_type
        self._data = data
        self._chunk_size = chunk_size
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._data):
            return b""
        if size is None or size < 0:
            size = len(self._data) - self._offset
        size = min(size, self._chunk_size)
        start = self._offset
        self._offset = min(len(self._data), self._offset + size)
        return self._data[start : self._offset]


@pytest.mark.asyncio
async def test_list_user_skills_returns_paginated_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        async def list_user_skills(
            self,
            user_id: str,
            skip: int = 0,
            limit: int = 100,
            disabled_skills=None,
            pinned_skill_names=None,
            favorite_skill_names=None,
            q: str | None = None,
            tags=None,
        ):
            assert user_id == "user-1"
            assert skip == 20
            assert limit == 10
            assert disabled_skills == ["archived"]
            assert pinned_skill_names == ["planner"]
            assert favorite_skill_names == ["writer"]
            assert q == "plan"
            assert tags == ["planning"]
            return [
                {
                    "skill_name": "planner",
                    "enabled": True,
                    "file_count": 1,
                    "file_paths": ["SKILL.md"],
                    "installed_from": "manual",
                    "published_marketplace_name": None,
                    "created_at": "2026-01-01T00:00:00Z",
                    "updated_at": "2026-01-02T00:00:00Z",
                    "is_pinned": True,
                    "is_favorite": False,
                }
            ]

        async def count_user_skills(self, user_id: str, q: str | None = None, tags=None):
            assert user_id == "user-1"
            assert q == "plan"
            assert tags == ["planning"]
            return 37

        async def count_disabled_user_skills(
            self,
            user_id: str,
            disabled_skills,
            q: str | None = None,
            tags=None,
        ):
            assert user_id == "user-1"
            assert disabled_skills == ["archived"]
            assert q == "plan"
            assert tags == ["planning"]
            return 0

        async def list_user_skill_tags(self, user_id: str):
            assert user_id == "user-1"
            return ["planning"]

        async def batch_get_skill_md_contents(self, skill_names, user_id: str):
            assert skill_names == ["planner"]
            assert user_id == "user-1"
            return {"planner": "---\nname: planner\ndescription: Plan work\ntags:\n- planning\n---"}

    class _FakeMarketplace:
        async def get_user_published_skills(self, user_id: str, *, skill_names=None):
            assert user_id == "user-1"
            assert skill_names == ["planner"]
            return {}

    monkeypatch.setattr(skill_route, "UserStorage", lambda: _FakeUserStorage())

    app = FastAPI()
    app.include_router(skill_route.router, prefix="/api/skills")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[skill_route.get_storage] = lambda: _FakeStorage()
    app.dependency_overrides[skill_route.get_marketplace_storage] = lambda: _FakeMarketplace()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/skills/?skip=20&limit=10&q=plan&tags=planning")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 37
    assert payload["skip"] == 20
    assert payload["limit"] == 10
    assert payload["enabled_count"] == 37
    assert payload["available_tags"] == ["planning"]
    assert [skill["skill_name"] for skill in payload["skills"]] == ["planner"]
    assert payload["skills"][0]["is_pinned"] is True
    assert payload["skills"][0]["is_favorite"] is False


@pytest.mark.asyncio
async def test_list_user_skills_offloads_skill_md_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        async def list_user_skills(
            self,
            user_id: str,
            skip: int = 0,
            limit: int = 100,
            disabled_skills=None,
            pinned_skill_names=None,
            favorite_skill_names=None,
            q: str | None = None,
            tags=None,
        ):
            return [
                {
                    "skill_name": "planner",
                    "enabled": True,
                    "file_count": 1,
                    "file_paths": ["SKILL.md"],
                }
            ]

        async def count_user_skills(self, user_id: str, q: str | None = None, tags=None):
            return 1

        async def count_disabled_user_skills(
            self,
            user_id: str,
            disabled_skills,
            q: str | None = None,
            tags=None,
        ):
            return 0

        async def list_user_skill_tags(self, user_id: str):
            return []

        async def batch_get_skill_md_contents(self, skill_names, user_id: str):
            return {"planner": "skill-md-content"}

    class _FakeMarketplace:
        async def get_user_published_skills(self, user_id: str, *, skill_names=None):
            assert skill_names == ["planner"]
            return {}

    import src.infra.skill.parser as parser_module

    offloaded_contents: list[str] = []

    def _parse_skill_md(content: str):
        return "planner", "Plan work", ["planning"]

    async def _record_run_blocking_io(func, *args, **kwargs):
        offloaded_contents.append(args[0])
        return func(*args, **kwargs)

    monkeypatch.setattr(parser_module, "parse_skill_md", _parse_skill_md)
    monkeypatch.setattr(skill_route, "run_blocking_io", _record_run_blocking_io)
    monkeypatch.setattr(skill_route, "UserStorage", lambda: _FakeUserStorage())

    app = FastAPI()
    app.include_router(skill_route.router, prefix="/api/skills")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[skill_route.get_storage] = lambda: _FakeStorage()
    app.dependency_overrides[skill_route.get_marketplace_storage] = lambda: _FakeMarketplace()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/skills/")

    assert response.status_code == 200
    assert offloaded_contents == ["skill-md-content"]


@pytest.mark.asyncio
async def test_list_user_skills_rejects_large_page_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        async def list_user_skill_tags(self, user_id: str):
            return []

    class _FakeMarketplace:
        async def get_user_published_skills(self, user_id: str, *, skill_names=None):
            return {}

    monkeypatch.setattr(skill_route, "UserStorage", lambda: _FakeUserStorage())

    app = FastAPI()
    app.include_router(skill_route.router, prefix="/api/skills")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[skill_route.get_storage] = lambda: _FakeStorage()
    app.dependency_overrides[skill_route.get_marketplace_storage] = lambda: _FakeMarketplace()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/skills/?limit=101")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_user_skills_bounds_metadata_lists_before_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _LargeMetadataUserDoc:
        metadata = {
            "disabled_skills": [f"disabled-{index}" for index in range(125)] + ["disabled-1"],
            "pinned_skill_names": [f"pinned-{index}" for index in range(125)] + ["pinned-1"],
            "favorite_skill_names": [f"favorite-{index}" for index in range(125)] + ["favorite-1"],
        }

    class _LargeMetadataUserStorage:
        async def get_by_id(self, user_id: str):
            assert user_id == "user-1"
            return _LargeMetadataUserDoc()

    class _FakeStorage:
        async def list_user_skill_tags(self, user_id: str):
            assert user_id == "user-1"
            return []

        async def list_user_skills(
            self,
            user_id: str,
            skip: int = 0,
            limit: int = 100,
            disabled_skills=None,
            pinned_skill_names=None,
            favorite_skill_names=None,
            q: str | None = None,
            tags=None,
        ):
            assert disabled_skills == [f"disabled-{index}" for index in range(100)]
            assert pinned_skill_names == [f"pinned-{index}" for index in range(100)]
            assert favorite_skill_names == [f"favorite-{index}" for index in range(100)]
            return []

        async def count_user_skills(self, user_id: str, q: str | None = None, tags=None):
            return 0

        async def count_disabled_user_skills(
            self,
            user_id: str,
            disabled_skills,
            q: str | None = None,
            tags=None,
        ):
            assert disabled_skills == [f"disabled-{index}" for index in range(100)]
            return 0

    class _FakeMarketplace:
        async def get_user_published_skills(self, user_id: str, *, skill_names=None):
            return {}

    monkeypatch.setattr(skill_route, "UserStorage", lambda: _LargeMetadataUserStorage())

    app = FastAPI()
    app.include_router(skill_route.router, prefix="/api/skills")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[skill_route.get_storage] = lambda: _FakeStorage()
    app.dependency_overrides[skill_route.get_marketplace_storage] = lambda: _FakeMarketplace()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/skills/")

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_preview_zip_rejects_oversized_upload_before_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _StorageShouldNotBeCalled:
        async def list_user_skills(self, user_id: str):
            raise AssertionError("storage should not be called for oversized uploads")

    monkeypatch.setattr(skill_route.settings, "S3_ENABLED", False, raising=False)
    monkeypatch.setattr(skill_route.settings, "FILE_UPLOAD_MAX_SIZE_DOCUMENT", 1, raising=False)
    monkeypatch.setattr(
        skill_route,
        "_parse_zip_skills",
        lambda _content: (_ for _ in ()).throw(
            AssertionError("oversized upload should not be parsed")
        ),
    )

    with pytest.raises(HTTPException) as exc:
        await skill_route.preview_zip_skills(
            file=_ChunkedUpload(filename="skills.zip", data=b"x" * (1024 * 1024 + 1)),
            user=_fake_user(),
            storage=_StorageShouldNotBeCalled(),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Failed to read file content"


def test_skill_upload_size_treats_string_false_as_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_route.settings, "S3_ENABLED", "false", raising=False)
    monkeypatch.setattr(skill_route.settings, "S3_MAX_FILE_SIZE", 99 * 1024 * 1024, raising=False)
    monkeypatch.setattr(skill_route.settings, "FILE_UPLOAD_MAX_SIZE_DOCUMENT", 1, raising=False)

    assert skill_route._get_skill_upload_max_size() == (1024 * 1024, 1)


def test_parse_zip_skills_rejects_oversized_uncompressed_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_route, "_get_skill_upload_max_size", lambda: (1024, 0))

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big-skill/SKILL.md", "---\nname: big\n---\n" + ("x" * 2048))

    with pytest.raises(ValueError, match="uncompressed content too large"):
        skill_route._parse_zip_skills(zip_buffer.getvalue())


def test_parse_zip_skills_rejects_oversized_single_member_before_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_route, "_get_skill_upload_max_size", lambda: (4096, 0))
    monkeypatch.setattr(skill_route, "_ZIP_MEMBER_MAX_BYTES", 8, raising=False)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("big-skill/SKILL.md", "---\nname: big\n---\n")
        archive.writestr("big-skill/huge.bin", b"x" * 16)

    with pytest.raises(ValueError, match="ZIP member too large"):
        skill_route._parse_zip_skills(zip_buffer.getvalue())


def test_parse_zip_skills_rejects_too_many_members_before_reading_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_route, "_get_skill_upload_max_size", lambda: (1024 * 1024, 1))
    monkeypatch.setattr(skill_route, "_ZIP_MAX_MEMBERS", 2, raising=False)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("many/SKILL.md", "---\nname: many\n---\n")
        archive.writestr("many/a.txt", "a")
        archive.writestr("many/b.txt", "b")

    with pytest.raises(ValueError, match="too many files"):
        skill_route._parse_zip_skills(zip_buffer.getvalue())


def test_parse_zip_skills_rejects_unsafe_member_paths() -> None:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("evil/SKILL.md", "---\nname: evil\n---\n")
        archive.writestr("evil/../outside.txt", "nope")

    with pytest.raises(ValueError, match="Unsafe ZIP member path"):
        skill_route._parse_zip_skills(zip_buffer.getvalue())


def test_parse_zip_preview_rejects_unsafe_member_paths() -> None:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("evil/SKILL.md", "---\nname: evil\n---\n")
        archive.writestr("/absolute.txt", "nope")

    with pytest.raises(ValueError, match="Unsafe ZIP member path"):
        skill_route._parse_zip_skill_preview(zip_buffer.getvalue())


def test_parse_zip_preview_skips_large_non_skill_members_before_reading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(skill_route, "_get_skill_upload_max_size", lambda: (4096, 0))

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "planner/SKILL.md",
            "---\nname: planner\ndescription: Plan work\n---\n",
        )
        archive.writestr("planner/assets/large.bin", b"x" * 3000)

    preview = skill_route._parse_zip_skill_preview(zip_buffer.getvalue())

    assert preview == [
        {
            "name": "planner",
            "description": "Plan work",
            "file_count": 2,
            "files": ["SKILL.md", "assets/large.bin"],
            "binary_files": ["assets/large.bin"],
        }
    ]


def test_parse_zip_skills_canonicalizes_lowercase_skill_md() -> None:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "planner/skill.md",
            "---\nname: planner\ndescription: Plan work\n---\n",
        )
        archive.writestr("planner/notes.md", "notes")

    skills = skill_route._parse_zip_skills(zip_buffer.getvalue())

    assert skills == [
        (
            "planner",
            {
                "SKILL.md": "---\nname: planner\ndescription: Plan work\n---\n",
                "notes.md": "notes",
            },
            {},
        )
    ]


def test_parse_zip_preview_canonicalizes_lowercase_skill_md() -> None:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "planner/skill.md",
            "---\nname: planner\ndescription: Plan work\n---\n",
        )

    preview = skill_route._parse_zip_skill_preview(zip_buffer.getvalue())

    assert preview == [
        {
            "name": "planner",
            "description": "Plan work",
            "file_count": 1,
            "files": ["SKILL.md"],
            "binary_files": [],
        }
    ]


@pytest.mark.asyncio
async def test_update_skill_preference_returns_updated_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        async def list_skill_file_paths(self, skill_name: str, user_id: str):
            assert skill_name == "planner"
            assert user_id == "user-1"
            return ["SKILL.md"]

        async def update_user_preference(self, *, user_id: str, skill_name: str, update):
            assert user_id == "user-1"
            assert skill_name == "planner"
            assert update == {"is_favorite": True, "is_pinned": None}
            return {"is_favorite": True, "is_pinned": False}

    monkeypatch.setattr(skill_route, "UserStorage", lambda: _FakeUserStorage())

    app = FastAPI()
    app.include_router(skill_route.router, prefix="/api/skills")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[skill_route.get_storage] = lambda: _FakeStorage()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.patch(
            "/api/skills/planner/preference",
            json={"is_favorite": True},
        )

    assert response.status_code == 200
    assert response.json() == {
        "skill_name": "planner",
        "is_favorite": True,
        "is_pinned": False,
    }


@pytest.mark.asyncio
async def test_get_user_skill_avoids_loading_all_file_contents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        async def get_skill_files(self, skill_name: str, user_id: str):
            raise AssertionError("skill detail should not load every file content")

        async def list_skill_file_paths(self, skill_name: str, user_id: str):
            assert skill_name == "planner"
            assert user_id == "user-1"
            return ["SKILL.md", "notes.md"]

        async def get_skill_file(self, skill_name: str, file_path: str, user_id: str):
            assert skill_name == "planner"
            assert file_path == "SKILL.md"
            assert user_id == "user-1"
            return "---\nname: planner\ndescription: Plan work\ntags:\n- planning\n---\n"

        async def get_skill_meta(self, skill_name: str, user_id: str):
            assert skill_name == "planner"
            assert user_id == "user-1"
            return None

        async def get_skill_file_stats(self, skill_name: str, user_id: str):
            assert skill_name == "planner"
            assert user_id == "user-1"
            return {
                "file_count": 2,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
            }

    class _FakeMarketplace:
        async def get_user_published_skills(self, user_id: str, *, skill_names=None):
            assert user_id == "user-1"
            assert skill_names == ["planner"]
            return {}

    monkeypatch.setattr(skill_route, "UserStorage", lambda: _FakeUserStorage())

    app = FastAPI()
    app.include_router(skill_route.router, prefix="/api/skills")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[skill_route.get_storage] = lambda: _FakeStorage()
    app.dependency_overrides[skill_route.get_marketplace_storage] = lambda: _FakeMarketplace()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/skills/planner")

    assert response.status_code == 200
    payload = response.json()
    assert payload["skill_name"] == "planner"
    assert payload["description"] == "Plan work"
    assert payload["tags"] == ["planning"]
    assert payload["files"] == ["SKILL.md", "notes.md"]


@pytest.mark.asyncio
async def test_get_user_skill_offloads_skill_md_parsing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStorage:
        async def list_skill_file_paths(self, skill_name: str, user_id: str):
            return ["SKILL.md"]

        async def get_skill_file(self, skill_name: str, file_path: str, user_id: str):
            return "skill-md-content"

        async def get_skill_meta(self, skill_name: str, user_id: str):
            return None

        async def get_skill_file_stats(self, skill_name: str, user_id: str):
            return {
                "file_count": 1,
                "created_at": None,
                "updated_at": None,
            }

    class _FakeMarketplace:
        async def get_user_published_skills(self, user_id: str, *, skill_names=None):
            assert skill_names == ["planner"]
            return {}

    import src.infra.skill.parser as parser_module

    offloaded_contents: list[str] = []

    def _parse_skill_md(content: str):
        return "planner", "Plan work", ["planning"]

    async def _record_run_blocking_io(func, *args, **kwargs):
        offloaded_contents.append(args[0])
        return func(*args, **kwargs)

    monkeypatch.setattr(parser_module, "parse_skill_md", _parse_skill_md)
    monkeypatch.setattr(skill_route, "run_blocking_io", _record_run_blocking_io)
    monkeypatch.setattr(skill_route, "UserStorage", lambda: _FakeUserStorage())

    app = FastAPI()
    app.include_router(skill_route.router, prefix="/api/skills")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[skill_route.get_storage] = lambda: _FakeStorage()
    app.dependency_overrides[skill_route.get_marketplace_storage] = lambda: _FakeMarketplace()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/api/skills/planner")

    assert response.status_code == 200
    assert offloaded_contents == ["skill-md-content"]


@pytest.mark.asyncio
async def test_batch_delete_skills_rejects_large_name_lists_before_storage() -> None:
    class _StorageShouldNotBeCalled:
        async def delete_skill_and_meta(self, *args, **kwargs):
            raise AssertionError("large batch should be rejected before storage access")

    with pytest.raises(HTTPException) as exc:
        await skill_route.batch_delete_skills(
            skill_route.BatchDeleteRequest(names=[f"skill-{index}" for index in range(101)]),
            user=_fake_user(),
            storage=_StorageShouldNotBeCalled(),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Cannot process more than 100 skills at once"


@pytest.mark.asyncio
async def test_batch_toggle_skills_rejects_large_name_lists_before_storage() -> None:
    class _StorageShouldNotBeCalled:
        async def list_skill_file_paths(self, *args, **kwargs):
            raise AssertionError("large batch should be rejected before storage access")

    with pytest.raises(HTTPException) as exc:
        await skill_route.batch_toggle_skills(
            skill_route.BatchToggleRequest(
                names=[f"skill-{index}" for index in range(101)],
                enabled=False,
            ),
            user=_fake_user(),
            storage=_StorageShouldNotBeCalled(),
        )

    assert exc.value.status_code == 400
    assert exc.value.detail == "Cannot process more than 100 skills at once"


@pytest.mark.asyncio
async def test_batch_toggle_skills_bounds_existing_disabled_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _LargeMetadataUserDoc:
        metadata = {"disabled_skills": [f"disabled-{index}" for index in range(150)]}

    class _LargeMetadataUserStorage:
        def __init__(self) -> None:
            self.updated: dict | None = None

        async def get_by_id(self, user_id: str):
            assert user_id == "user-1"
            return _LargeMetadataUserDoc()

        async def update_metadata(self, user_id: str, metadata: dict):
            assert user_id == "user-1"
            self.updated = metadata

    class _FakeStorage:
        async def list_skill_file_paths(self, skill_name: str, user_id: str):
            assert skill_name == "planner"
            assert user_id == "user-1"
            return ["SKILL.md"]

        async def invalidate_user_cache(self, user_id: str):
            assert user_id == "user-1"

    user_storage = _LargeMetadataUserStorage()
    monkeypatch.setattr(skill_route, "UserStorage", lambda: user_storage)

    result = await skill_route.batch_toggle_skills(
        skill_route.BatchToggleRequest(names=["planner"], enabled=False),
        user=_fake_user(),
        storage=_FakeStorage(),
    )

    assert result == {"updated": ["planner"], "errors": []}
    assert user_storage.updated is not None
    assert user_storage.updated["disabled_skills"][0] == "planner"
    assert len(user_storage.updated["disabled_skills"]) == 100
