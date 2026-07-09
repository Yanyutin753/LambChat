from __future__ import annotations

import sys
from pathlib import Path

import pytest

from src.kernel.extensions.manifest import PluginInstallType, PluginManifest
from src.kernel.extensions.module_loader import load_plugin_attr, load_plugin_module


def _manifest(plugin_root: Path) -> PluginManifest:
    return PluginManifest(
        id="agent_team",
        name="Agent Team",
        version="1.0.0",
        api_version="v1",
        install_type=PluginInstallType.SYSTEM_BUILTIN,
        package_source_path=str(plugin_root),
    )


def test_plugin_relative_module_failed_import_does_not_poison_cache(tmp_path: Path) -> None:
    plugin_root = tmp_path / "agent_team"
    runtime_dir = plugin_root / "backend" / "runtime"
    runtime_dir.mkdir(parents=True)
    module_file = runtime_dir / "graph.py"
    module_file.write_text("raise RuntimeError('boom')\nclass TeamAgent: ...\n", encoding="utf-8")
    manifest = _manifest(plugin_root)

    with pytest.raises(RuntimeError, match="boom"):
        load_plugin_attr(manifest, "./backend/runtime/graph.py:TeamAgent")

    assert not any(
        name.startswith("_lambchat_plugin_agent_team_")
        and getattr(module, "__file__", None) == str(module_file)
        for name, module in sys.modules.items()
    )

    module_file.write_text("class TeamAgent: ...\n", encoding="utf-8")

    assert (
        load_plugin_attr(manifest, "./backend/runtime/graph.py:TeamAgent").__name__ == "TeamAgent"
    )


def test_plugin_relative_attr_miss_reloads_stale_cached_module(tmp_path: Path) -> None:
    plugin_root = tmp_path / "agent_team"
    runtime_dir = plugin_root / "backend" / "runtime"
    runtime_dir.mkdir(parents=True)
    module_file = runtime_dir / "graph.py"
    module_file.write_text("VALUE = 1\n", encoding="utf-8")
    manifest = _manifest(plugin_root)

    module = load_plugin_module(manifest, "./backend/runtime/graph.py")
    assert module.VALUE == 1

    module_file.write_text("class TeamAgent: ...\n", encoding="utf-8")

    assert (
        load_plugin_attr(manifest, "./backend/runtime/graph.py:TeamAgent").__name__ == "TeamAgent"
    )
