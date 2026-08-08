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
