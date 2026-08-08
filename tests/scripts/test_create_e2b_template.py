from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


class _RecordingBuilder:
    def __init__(self) -> None:
        self.base: str | None = None
        self.commands: list[str] = []
        self.pip_packages: list[str] = []

    def from_template(self, template: str) -> _RecordingBuilder:
        self.base = template
        return self

    def run_cmd(self, command: str) -> _RecordingBuilder:
        self.commands.append(command)
        return self

    def pip_install(self, packages: list[str]) -> _RecordingBuilder:
        self.pip_packages.extend(packages)
        return self


def test_build_template_installs_issue_199_commands() -> None:
    from scripts.create_e2b_template import EXTRA_PIP_PACKAGES, build_template

    builder = _RecordingBuilder()

    result = build_template(builder)

    assert result is builder
    assert builder.base == "code-interpreter-v1"
    apt = next(command for command in builder.commands if "apt-get install" in command)
    assert "ripgrep" in apt
    assert "librsvg2-bin" in apt
    assert builder.pip_packages == EXTRA_PIP_PACKAGES


def test_build_candidate_uses_unique_tag_and_writes_secret_free_manifest(
    tmp_path: Path,
) -> None:
    from scripts import create_e2b_template as module

    calls: list[dict[str, Any]] = []

    class _FakeTemplateApi:
        @staticmethod
        def build(template: object, name: str, **kwargs: Any) -> object:
            calls.append({"template": template, "name": name, **kwargs})
            return SimpleNamespace(
                template_id="tmpl_123",
                build_id="build_456",
                name=name,
                alias=name,
                tags=kwargs["tags"],
            )

    manifest_path = module.build_candidate(
        "candidate-20260808210000",
        "e2b-secret-key",
        manifest_dir=tmp_path,
        template_api=_FakeTemplateApi,
        template_builder=_RecordingBuilder(),
        build_logger=lambda entry: None,
    )

    assert calls[0]["name"] == "lambchat-prod"
    assert calls[0]["tags"] == ["candidate-20260808210000"]
    assert calls[0]["cpu_count"] == module.CPU_COUNT
    assert calls[0]["memory_mb"] == module.MEMORY_MB
    assert calls[0]["api_key"] == "e2b-secret-key"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["template_id"] == "tmpl_123"
    assert manifest["build_id"] == "build_456"
    assert manifest["immutable_ref"] == "lambchat-prod:build_456"
    assert manifest["rollout_id"]
    assert "e2b-secret-key" not in manifest_path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_resolve_api_key_uses_database_first_service_without_printing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    from scripts.create_e2b_template import resolve_e2b_api_key

    class _FakeSettingsService:
        async def get_raw(self, key: str) -> str:
            assert key == "E2B_API_KEY"
            return "e2b-database-secret"

    assert await resolve_e2b_api_key(_FakeSettingsService()) == "e2b-database-secret"
    assert "e2b-database-secret" not in capsys.readouterr().out


def _write_candidate_manifest(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "rollout_id": "rollout-1",
                "candidate_tag": "candidate-1",
                "template_name": "lambchat-prod",
                "template_id": "tmpl_123",
                "build_id": "build_456",
                "immutable_ref": "lambchat-prod:build_456",
            }
        ),
        encoding="utf-8",
    )


class _RecordingCommands:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls: list[str] = []

    def run(self, command: str) -> object:
        self.calls.append(command)
        if self.failure is not None:
            raise self.failure
        return SimpleNamespace(exit_code=0)


class _RecordingSandbox:
    def __init__(self, failure: Exception | None = None) -> None:
        self.commands = _RecordingCommands(failure)
        self.killed = False

    def kill(self) -> None:
        self.killed = True


def test_verify_manifest_smokes_immutable_build_and_always_kills(tmp_path: Path) -> None:
    from scripts.create_e2b_template import verify_manifest

    manifest_path = tmp_path / "candidate.json"
    _write_candidate_manifest(manifest_path)
    sandbox = _RecordingSandbox()
    creates: list[tuple[str, dict[str, object]]] = []

    class _FakeSandboxApi:
        @staticmethod
        def create(reference: str, **kwargs: object) -> _RecordingSandbox:
            creates.append((reference, kwargs))
            return sandbox

    verify_manifest(manifest_path, "e2b-secret", sandbox_api=_FakeSandboxApi)

    assert creates == [("lambchat-prod:build_456", {"timeout": 300, "api_key": "e2b-secret"})]
    command = sandbox.commands.calls[0]
    assert "command -v rg" in command
    assert "command -v rsvg-convert" in command
    assert "rsvg-convert" in command
    assert "test -s" in command
    assert sandbox.killed is True
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["verified_build_id"] == "build_456"
    assert manifest["verified_at"]


def test_verify_manifest_failure_kills_and_leaves_no_verification_evidence(
    tmp_path: Path,
) -> None:
    from scripts.create_e2b_template import verify_manifest

    manifest_path = tmp_path / "candidate.json"
    _write_candidate_manifest(manifest_path)
    sandbox = _RecordingSandbox(RuntimeError("smoke failed"))

    class _FakeSandboxApi:
        @staticmethod
        def create(reference: str, **kwargs: object) -> _RecordingSandbox:
            return sandbox

    with pytest.raises(RuntimeError, match="smoke failed"):
        verify_manifest(manifest_path, "e2b-secret", sandbox_api=_FakeSandboxApi)

    assert sandbox.killed is True
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert "verified_build_id" not in manifest
    assert "verified_at" not in manifest


def _matches(document: dict[str, object] | None, query: dict[str, object]) -> bool:
    if document is None:
        return False
    return all(document.get(key) == value for key, value in query.items())


class _FakeSettingsCollection:
    def __init__(self, document: dict[str, object] | None) -> None:
        self.document = dict(document) if document else None

    async def find_one(self, query: dict[str, object]) -> dict[str, object] | None:
        return dict(self.document) if _matches(self.document, query) else None

    async def replace_one(
        self,
        query: dict[str, object],
        replacement: dict[str, object],
    ) -> object:
        if not _matches(self.document, query):
            return SimpleNamespace(matched_count=0)
        self.document = dict(replacement)
        return SimpleNamespace(matched_count=1)

    async def insert_one(self, document: dict[str, object]) -> object:
        if self.document is not None:
            raise RuntimeError("duplicate key")
        self.document = dict(document)
        return SimpleNamespace(inserted_id=document["_id"])

    async def delete_one(self, query: dict[str, object]) -> object:
        if not _matches(self.document, query):
            return SimpleNamespace(deleted_count=0)
        self.document = None
        return SimpleNamespace(deleted_count=1)


class _FakeSettingsStorage:
    def __init__(self, collection: _FakeSettingsCollection) -> None:
        self.collection = collection

    def _get_collection(self) -> _FakeSettingsCollection:
        return self.collection


class _FakeSettingsService:
    def __init__(self, collection: _FakeSettingsCollection) -> None:
        self._storage = _FakeSettingsStorage(collection)
        self.published: list[tuple[str, object]] = []

    async def get_raw(self, key: str) -> str:
        assert key == "E2B_TEMPLATE"
        document = self._storage.collection.document
        return str(document["value"]) if document else "base"

    async def _publish_change(self, key: str, value: object) -> None:
        self.published.append((key, value))


@pytest.mark.asyncio
async def test_pin_is_cas_guarded_and_preserves_first_rollback_baseline(
    tmp_path: Path,
) -> None:
    from scripts.create_e2b_template import pin_effective_configuration

    manifest_path = tmp_path / "candidate.json"
    _write_candidate_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({"verified_build_id": "build_456", "verified_at": "now"})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("PORT=8000\nE2B_TEMPLATE=base\n", encoding="utf-8")
    original_document = {
        "_id": "E2B_TEMPLATE",
        "value": "base",
        "updated_at": "before",
        "updated_by": "admin",
    }
    collection = _FakeSettingsCollection(original_document)
    service = _FakeSettingsService(collection)

    await pin_effective_configuration(manifest_path, env_file, settings_service=service)
    first_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    await pin_effective_configuration(manifest_path, env_file, settings_service=service)
    second_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert collection.document is not None
    assert collection.document["value"] == "lambchat-prod:build_456"
    assert env_file.read_text(encoding="utf-8") == (
        "PORT=8000\nE2B_TEMPLATE=lambchat-prod:build_456\n"
    )
    assert first_manifest["configuration_baseline"] == second_manifest["configuration_baseline"]
    assert first_manifest["configuration_baseline"]["db_document"] == original_document
    assert first_manifest["configuration_baseline"]["env_previous_line"] == "E2B_TEMPLATE=base"
    assert second_manifest["pinned_ref"] == "lambchat-prod:build_456"


@pytest.mark.asyncio
async def test_restore_recovers_original_sources_and_invalidates_stale_evidence(
    tmp_path: Path,
) -> None:
    from scripts.create_e2b_template import (
        pin_effective_configuration,
        restore_effective_configuration,
    )

    manifest_path = tmp_path / "candidate.json"
    _write_candidate_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({"verified_build_id": "build_456", "verified_at": "now"})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("E2B_TEMPLATE=base\n", encoding="utf-8")
    original_document = {
        "_id": "E2B_TEMPLATE",
        "value": "base",
        "updated_at": "before",
        "updated_by": "admin",
    }
    collection = _FakeSettingsCollection(original_document)
    service = _FakeSettingsService(collection)
    await pin_effective_configuration(manifest_path, env_file, settings_service=service)
    pinned = json.loads(manifest_path.read_text(encoding="utf-8"))
    pinned.update(
        {
            "effective_ref_verified_at": "effective",
            "effective_ref_build_id": "build_456",
            "health_checked_at": "healthy",
            "health_build_id": "build_456",
            "health_ref": "lambchat-prod:build_456",
        }
    )
    manifest_path.write_text(json.dumps(pinned), encoding="utf-8")

    await restore_effective_configuration(manifest_path, settings_service=service)

    assert collection.document == original_document
    assert env_file.read_text(encoding="utf-8") == "E2B_TEMPLATE=base\n"
    restored = json.loads(manifest_path.read_text(encoding="utf-8"))
    for field in (
        "pinned_ref",
        "effective_ref_verified_at",
        "effective_ref_build_id",
        "health_checked_at",
        "health_build_id",
        "health_ref",
    ):
        assert field not in restored


@pytest.mark.asyncio
async def test_restore_refuses_to_overwrite_later_administrator_edit(tmp_path: Path) -> None:
    from scripts.create_e2b_template import (
        pin_effective_configuration,
        restore_effective_configuration,
    )

    manifest_path = tmp_path / "candidate.json"
    _write_candidate_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({"verified_build_id": "build_456", "verified_at": "now"})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("E2B_TEMPLATE=base\n", encoding="utf-8")
    collection = _FakeSettingsCollection(
        {"_id": "E2B_TEMPLATE", "value": "base", "updated_at": "before"}
    )
    service = _FakeSettingsService(collection)
    await pin_effective_configuration(manifest_path, env_file, settings_service=service)
    assert collection.document is not None
    collection.document["value"] = "administrator-template"

    with pytest.raises(RuntimeError, match="concurrent E2B_TEMPLATE edit"):
        await restore_effective_configuration(manifest_path, settings_service=service)

    assert collection.document["value"] == "administrator-template"


class _FakeHttpClient:
    async def get(self, url: str) -> object:
        assert url == "http://127.0.0.1:8000/health"
        return SimpleNamespace(status_code=200)


@pytest.mark.asyncio
async def test_effective_health_and_promotion_are_bound_to_current_build(
    tmp_path: Path,
) -> None:
    from scripts.create_e2b_template import (
        pin_effective_configuration,
        promote_manifest,
        record_health,
        verify_effective_configuration,
    )

    manifest_path = tmp_path / "candidate.json"
    _write_candidate_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update({"verified_build_id": "build_456", "verified_at": "now"})
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    env_file = tmp_path / ".env"
    env_file.write_text("E2B_TEMPLATE=base\n", encoding="utf-8")
    collection = _FakeSettingsCollection(
        {"_id": "E2B_TEMPLATE", "value": "base", "updated_at": "before"}
    )
    service = _FakeSettingsService(collection)
    await pin_effective_configuration(manifest_path, env_file, settings_service=service)
    await verify_effective_configuration(manifest_path, settings_service=service)
    await record_health(
        manifest_path,
        "http://127.0.0.1:8000/health",
        http_client=_FakeHttpClient(),
    )
    promotions: list[tuple[str, str, str]] = []

    class _FakeTemplateApi:
        @staticmethod
        def assign_tags(reference: str, tag: str, *, api_key: str) -> object:
            promotions.append((reference, tag, api_key))
            return SimpleNamespace(build_id="build_456", tags=["production"])

    await promote_manifest(
        manifest_path,
        "e2b-secret",
        settings_service=service,
        template_api=_FakeTemplateApi,
    )

    assert promotions == [("lambchat-prod:build_456", "production", "e2b-secret")]
    promoted = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert promoted["promoted_build_id"] == "build_456"


@pytest.mark.asyncio
async def test_promotion_rejects_stale_evidence_after_administrator_edit(
    tmp_path: Path,
) -> None:
    from scripts.create_e2b_template import promote_manifest

    manifest_path = tmp_path / "candidate.json"
    _write_candidate_manifest(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        {
            "verified_build_id": "build_456",
            "verified_at": "verified",
            "pinned_ref": "lambchat-prod:build_456",
            "pinned_build_id": "build_456",
            "effective_ref_verified_at": "effective",
            "effective_ref_build_id": "build_456",
            "health_checked_at": "healthy",
            "health_build_id": "build_456",
            "health_ref": "lambchat-prod:build_456",
        }
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    collection = _FakeSettingsCollection({"_id": "E2B_TEMPLATE", "value": "administrator-template"})
    service = _FakeSettingsService(collection)

    class _RejectUnexpectedPromotion:
        @staticmethod
        def assign_tags(*args: object, **kwargs: object) -> object:
            raise AssertionError("stale evidence must not promote")

    with pytest.raises(RuntimeError, match="effective E2B_TEMPLATE changed"):
        await promote_manifest(
            manifest_path,
            "e2b-secret",
            settings_service=service,
            template_api=_RejectUnexpectedPromotion,
        )


@pytest.mark.asyncio
async def test_cli_verify_dispatches_manifest_with_database_first_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from scripts import create_e2b_template as module

    manifest_path = tmp_path / "candidate.json"
    _write_candidate_manifest(manifest_path)
    calls: list[tuple[Path, str]] = []

    async def fake_resolve() -> str:
        return "e2b-database-secret"

    def fake_verify(path: Path, api_key: str) -> None:
        calls.append((path, api_key))

    monkeypatch.setattr(module, "resolve_e2b_api_key", fake_resolve)
    monkeypatch.setattr(module, "verify_manifest", fake_verify)

    result = await module.async_main(["verify", "--manifest", str(manifest_path)])

    assert result == 0
    assert calls == [(manifest_path, "e2b-database-secret")]
