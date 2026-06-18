"""Runtime context exposed to folder-based plugin code."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.kernel.extensions.manifest import PluginManifest
from src.kernel.extensions.resources import PluginResourceLedger


@dataclass(frozen=True)
class PluginContext:
    """Restricted context object for plugin routes, tools, and lifecycle hooks."""

    manifest: PluginManifest
    data_dir: Path
    settings: Any
    resources: PluginResourceLedger

    @property
    def plugin_id(self) -> str:
        return self.manifest.id

    @property
    def version(self) -> str:
        return self.manifest.version

    def data_path(self, *parts: str) -> Path:
        candidate = self.data_dir.joinpath(*parts).resolve()
        try:
            candidate.relative_to(self.data_dir.resolve())
        except ValueError as exc:
            raise ValueError("plugin data path escapes plugin-data directory") from exc
        return candidate

    def open_data_file(self, *parts: str, mode: str = "r", encoding: str = "utf-8"):
        path = self.data_path(*parts)
        if any(flag in mode for flag in ("w", "a", "+")):
            path.parent.mkdir(parents=True, exist_ok=True)
        return path.open(mode=mode, encoding=encoding)


def build_plugin_context(
    *,
    manifest: PluginManifest,
    resource_ledger: PluginResourceLedger,
    manifests: tuple[PluginManifest, ...],
) -> PluginContext:
    if not manifest.package_data_dir:
        raise ValueError(f"plugin {manifest.id} does not declare a package data directory")
    from src.infra.extensions.plugin_settings import PluginSettingsResolver

    return PluginContext(
        manifest=manifest,
        data_dir=Path(manifest.package_data_dir).resolve(),
        settings=PluginSettingsResolver(plugin_id=manifest.id, manifests=manifests),
        resources=resource_ledger,
    )
