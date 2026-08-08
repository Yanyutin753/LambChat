"""Checks that dependency metadata is portable across build environments."""

from __future__ import annotations

import tomllib
from pathlib import Path
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_project_dependencies_do_not_reference_local_paths() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

    local_dependencies = []
    for dependency in pyproject["project"]["dependencies"]:
        if " @ " not in dependency:
            continue

        _name, reference = dependency.split(" @ ", 1)
        parsed = urlparse(reference)
        if parsed.scheme == "file":
            local_dependencies.append(dependency)

    assert local_dependencies == []


def test_deepagents_targets_supported_v0_7_line() -> None:
    """Deepagents stays on the explicitly migrated v0.7 release line."""
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())

    dependencies = pyproject["project"]["dependencies"]
    deepagents = next(item for item in dependencies if item.startswith("deepagents"))

    assert deepagents == "deepagents>=0.7.5,<0.8"
