"""Filesystem-backed plugin data directory service."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.kernel.extensions.packages import PluginFolderDescriptor

PLUGIN_DATA_SUBDIRS = (
    "config",
    "state",
    "storage",
    "cache",
    "logs",
    "uploads",
    "migrations",
    "backups",
)


@dataclass(frozen=True)
class PluginDataSnapshot:
    plugin_id: str
    data_dir: str
    exists: bool
    subdirs: list[str]
    defaults_path: str
    current_path: str
    runtime_state_path: str
    file_count: int
    total_bytes: int
    backup_count: int = 0
    last_backup_path: str | None = None


class PluginDataService:
    """Create and summarize plugin-data/{plugin_id} without exposing arbitrary paths."""

    def __init__(self, *, data_root: Path) -> None:
        self.data_root = data_root.resolve()

    def ensure_for_descriptor(self, descriptor: PluginFolderDescriptor) -> PluginDataSnapshot:
        data_dir = self._plugin_data_dir(descriptor.plugin_id)
        data_dir.mkdir(parents=True, exist_ok=True)
        for subdir in PLUGIN_DATA_SUBDIRS:
            (data_dir / subdir).mkdir(parents=True, exist_ok=True)
        self._copy_template_if_needed(descriptor.folder / "plugin-data-template", data_dir)
        manifest = descriptor.manifest
        defaults = _manifest_defaults(manifest) if manifest is not None else {}
        self._write_json_if_missing(data_dir / "config" / "defaults.json", defaults)
        self._write_json_if_missing(data_dir / "config" / "current.json", {})
        self._write_json_if_missing(
            data_dir / "state" / "runtime.json",
            {
                "plugin_id": descriptor.plugin_id,
                "package_source_type": descriptor.source_type,
                "package_source_path": str(descriptor.folder),
            },
        )
        return self.snapshot(descriptor.plugin_id)

    def snapshot(self, plugin_id: str) -> PluginDataSnapshot:
        data_dir = self._plugin_data_dir(plugin_id)
        file_count = 0
        total_bytes = 0
        if data_dir.exists():
            for path in data_dir.rglob("*"):
                if path.is_file():
                    file_count += 1
                    total_bytes += path.stat().st_size
        backups_dir = data_dir / "backups"
        backups = sorted(
            (path for path in backups_dir.glob("current-config-*.json") if path.is_file()),
            key=lambda path: path.name,
        ) if backups_dir.exists() else []
        return PluginDataSnapshot(
            plugin_id=plugin_id,
            data_dir=str(data_dir),
            exists=data_dir.exists(),
            subdirs=[subdir for subdir in PLUGIN_DATA_SUBDIRS if (data_dir / subdir).exists()],
            defaults_path=str(data_dir / "config" / "defaults.json"),
            current_path=str(data_dir / "config" / "current.json"),
            runtime_state_path=str(data_dir / "state" / "runtime.json"),
            file_count=file_count,
            total_bytes=total_bytes,
            backup_count=len(backups),
            last_backup_path=str(backups[-1]) if backups else None,
        )

    def reset_current_config(self, plugin_id: str) -> PluginDataSnapshot:
        data_dir = self._plugin_data_dir(plugin_id)
        current_path = data_dir / "config" / "current.json"
        current_path.parent.mkdir(parents=True, exist_ok=True)
        self._backup_current_config(current_path, data_dir / "backups")
        current_path.write_text("{}\n", encoding="utf-8")
        return self.snapshot(plugin_id)

    def _backup_current_config(self, current_path: Path, backups_dir: Path) -> None:
        if not current_path.exists() or not current_path.is_file():
            return
        backups_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = backups_dir / f"current-config-{timestamp}.json"
        shutil.copy2(current_path, backup_path)

    def _plugin_data_dir(self, plugin_id: str) -> Path:
        if any(part in {"", ".", ".."} for part in plugin_id.replace("\\", "/").split("/")):
            raise ValueError("plugin id must be a safe path segment")
        path = (self.data_root / plugin_id).resolve()
        try:
            path.relative_to(self.data_root)
        except ValueError as exc:
            raise ValueError("plugin data path escapes plugin-data root") from exc
        return path

    def _copy_template_if_needed(self, template_dir: Path, data_dir: Path) -> None:
        if not template_dir.exists():
            return
        if template_dir.is_symlink():
            raise ValueError("plugin-data-template symlinks are not allowed")
        for source in template_dir.rglob("*"):
            if source.is_symlink():
                raise ValueError("plugin-data-template symlinks are not allowed")
            relative = source.relative_to(template_dir)
            target = (data_dir / relative).resolve()
            try:
                target.relative_to(data_dir)
            except ValueError as exc:
                raise ValueError("plugin-data-template escapes plugin data dir") from exc
            if source.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            elif not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def _write_json_if_missing(self, path: Path, payload: dict[str, Any]) -> None:
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _manifest_defaults(manifest) -> dict[str, Any]:
    defaults: dict[str, Any] = dict(getattr(manifest, "package_config_defaults", {}) or {})
    for setting in getattr(manifest, "settings", []) or []:
        if setting.key in defaults:
            continue
        if getattr(setting, "sensitive", False):
            defaults[setting.key] = "********" if setting.default not in (None, "") else ""
        else:
            defaults[setting.key] = setting.default
    return defaults
