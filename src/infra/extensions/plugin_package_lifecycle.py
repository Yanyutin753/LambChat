"""Controlled lifecycle operations for local plugin package folders."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.infra.extensions.plugin_package_integrity import (
    PluginPackageIntegrity,
    build_package_integrity,
)


@dataclass(frozen=True)
class PluginPackageUninstallResult:
    plugin_id: str
    action: str
    package_source_path: str | None
    archive_path: str | None
    data_dir: str | None
    data_retained: bool
    integrity: PluginPackageIntegrity | None
    warnings: list[str]


@dataclass(frozen=True)
class ArchivedPluginPackage:
    archive_id: str
    plugin_id: str
    archive_path: str
    manifest_path: str
    data_dir: str
    archived_at: datetime | None
    integrity: PluginPackageIntegrity
    valid: bool
    errors: list[str]


@dataclass(frozen=True)
class PluginPackageRestoreResult:
    plugin_id: str
    archive_id: str
    status: str
    archive_path: str
    target_path: str
    data_dir: str
    integrity: PluginPackageIntegrity
    warnings: list[str]


class PluginPackageLifecycleService:
    """Apply package-folder uninstall actions without touching plugin-data."""

    def __init__(self, *, plugin_root: Path, data_root: Path) -> None:
        self.plugin_root = plugin_root.resolve()
        self.data_root = data_root.resolve()
        self.installed_root = (self.plugin_root / "installed").resolve()
        self.archived_root = (self.plugin_root / "archived").resolve()

    def uninstall_package(self, manifest) -> PluginPackageUninstallResult:
        plugin_id = str(getattr(manifest, "id", "") or "")
        source_type = str(getattr(manifest, "package_source_type", "") or "")
        source_path = getattr(manifest, "package_source_path", None)
        data_dir = getattr(manifest, "package_data_dir", None)
        warnings = [
            "plugin-data is retained by default and is not physically deleted.",
        ]
        if source_type != "installed" or not source_path:
            warnings.append("only user-installed package folders are archived by uninstall execution.")
            return PluginPackageUninstallResult(
                plugin_id=plugin_id,
                action="state_only",
                package_source_path=source_path,
                archive_path=None,
                data_dir=data_dir,
                data_retained=bool(data_dir),
                integrity=build_package_integrity(Path(source_path)) if source_path else None,
                warnings=warnings,
            )

        source = Path(source_path).resolve()
        expected_source = (self.installed_root / plugin_id).resolve()
        self._ensure_inside(source, self.installed_root, "installed package source")
        if source != expected_source:
            raise ValueError("installed package source does not match plugin id")
        if not source.exists() or not source.is_dir():
            warnings.append("installed package folder was already absent.")
            return PluginPackageUninstallResult(
                plugin_id=plugin_id,
                action="package_missing",
                package_source_path=str(source),
                archive_path=None,
                data_dir=data_dir,
                data_retained=bool(data_dir),
                integrity=None,
                warnings=warnings,
            )
        if source.is_symlink():
            raise ValueError("installed package source symlinks are not allowed")

        archive = self._archive_target(plugin_id)
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(archive))
        return PluginPackageUninstallResult(
            plugin_id=plugin_id,
            action="archive_package_folder",
            package_source_path=str(source),
            archive_path=str(archive),
            data_dir=data_dir,
            data_retained=bool(data_dir),
            integrity=build_package_integrity(archive),
            warnings=warnings,
        )

    def list_archived_packages(self) -> list[ArchivedPluginPackage]:
        if not self.archived_root.exists():
            return []
        if self.archived_root.is_symlink():
            raise ValueError("archived package root symlinks are not allowed")
        packages: list[ArchivedPluginPackage] = []
        for folder in sorted(self.archived_root.iterdir(), key=lambda item: item.name):
            if not folder.is_dir():
                continue
            packages.append(self._archived_package(folder.resolve()))
        return packages

    def restore_archived_package(self, archive_id: str) -> PluginPackageRestoreResult:
        archive = (self.archived_root / _safe_segment(archive_id)).resolve()
        self._ensure_inside(archive, self.archived_root, "archive package source")
        package = self._archived_package(archive)
        if not package.valid:
            raise ValueError("archived package is invalid: " + "; ".join(package.errors))
        target = (self.installed_root / package.plugin_id).resolve()
        self._ensure_inside(target, self.installed_root, "restore package target")
        if target.exists():
            raise ValueError(f"installed package already exists: {package.plugin_id}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(archive), str(target))
        return PluginPackageRestoreResult(
            plugin_id=package.plugin_id,
            archive_id=archive_id,
            status="restored",
            archive_path=str(archive),
            target_path=str(target),
            data_dir=package.data_dir,
            integrity=build_package_integrity(target),
            warnings=[
                "plugin-data was preserved and reused; restore does not overwrite runtime data.",
                "restored plugins remain disabled until an administrator enables them.",
            ],
        )

    def _archive_target(self, plugin_id: str) -> Path:
        safe_plugin_id = _safe_segment(plugin_id)
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        base = (self.archived_root / f"{safe_plugin_id}-{timestamp}").resolve()
        self._ensure_inside(base, self.archived_root, "archive package target")
        candidate = base
        counter = 1
        while candidate.exists():
            candidate = (self.archived_root / f"{safe_plugin_id}-{timestamp}-{counter}").resolve()
            self._ensure_inside(candidate, self.archived_root, "archive package target")
            counter += 1
        return candidate

    def _archived_package(self, folder: Path) -> ArchivedPluginPackage:
        self._ensure_inside(folder, self.archived_root, "archive package source")
        errors: list[str] = []
        if folder.is_symlink():
            errors.append("archived package folder symlinks are not allowed")
        manifest_path = (folder / "plugin.yaml").resolve()
        if not manifest_path.is_file():
            errors.append("plugin.yaml is missing")
        plugin_id = _plugin_id_from_archive_id(folder.name)
        if manifest_path.is_file():
            try:
                plugin_id = _read_plugin_id(manifest_path)
            except ValueError as exc:
                errors.append(str(exc))
        data_dir = (self.data_root / plugin_id).resolve()
        try:
            data_dir.relative_to(self.data_root)
        except ValueError:
            errors.append("plugin data path escapes plugin-data root")
        return ArchivedPluginPackage(
            archive_id=folder.name,
            plugin_id=plugin_id,
            archive_path=str(folder),
            manifest_path=str(manifest_path),
            data_dir=str(data_dir),
            archived_at=_archived_at_from_id(folder.name, plugin_id),
            integrity=build_package_integrity(folder),
            valid=not errors,
            errors=errors,
        )

    def _ensure_inside(self, path: Path, root: Path, label: str) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError(f"{label} escapes plugin package root") from exc


def _safe_segment(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("plugin id must be a safe path segment")
    return normalized


def _plugin_id_from_archive_id(archive_id: str) -> str:
    parts = archive_id.split("-")
    for index, part in enumerate(parts):
        if len(part) == 14 and part.isdigit():
            return "-".join(parts[:index]) or archive_id
    return archive_id


def _archived_at_from_id(archive_id: str, plugin_id: str) -> datetime | None:
    prefix = f"{plugin_id}-"
    if not archive_id.startswith(prefix):
        return None
    raw = archive_id[len(prefix):].split("-", 1)[0]
    if len(raw) != 14 or not raw.isdigit():
        return None
    return datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def _read_plugin_id(manifest_path: Path) -> str:
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() == "id":
            plugin_id = value.strip().strip('"\'')
            return _safe_segment(plugin_id)
    raise ValueError("plugin.yaml id is missing")
