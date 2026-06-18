"""Local folder plugin package import staging and install helpers."""

from __future__ import annotations

import shutil
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from src.infra.extensions.plugin_data import PluginDataService
from src.infra.extensions.plugin_package_integrity import (
    PluginPackageIntegrity,
    build_package_integrity,
)
from src.kernel.extensions.packages import PluginFolderDescriptor, PluginPackageScanner

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 2000
MAX_PACKAGE_FILES = MAX_ARCHIVE_MEMBERS
MAX_PACKAGE_BYTES = MAX_ARCHIVE_BYTES
SUPPORTED_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")


@dataclass(frozen=True)
class PluginPackageImportResult:
    plugin_id: str
    status: str
    dry_run: bool
    source_path: str
    target_path: str
    data_dir: str
    descriptor: PluginFolderDescriptor
    integrity: PluginPackageIntegrity
    actions: list[str]
    warnings: list[str]


class PluginPackageImportService:
    """Install a validated local plugin folder into plugins/installed.

    This service intentionally does not hot-load code or install dependencies.
    The package becomes visible after the next package scan/startup cycle.
    """

    def __init__(self, *, plugin_root: Path, data_root: Path) -> None:
        self.plugin_root = plugin_root.resolve()
        self.data_root = data_root.resolve()
        self.installed_root = (self.plugin_root / "installed").resolve()

    def import_folder(self, source_path: Path, *, dry_run: bool = True) -> PluginPackageImportResult:
        source = source_path.resolve()
        if source.is_file() and _is_supported_archive(source):
            return self._import_archive(source, dry_run=dry_run)
        descriptor = self._validate_source(source)
        integrity = build_package_integrity(source)
        plugin_id = descriptor.plugin_id
        target = (self.installed_root / plugin_id).resolve()
        self._ensure_inside(target, self.installed_root)
        warnings = [
            "Local package import does not hot-load code; restart or rescan before execution.",
            "Imported plugins are user-installed folder packages and should remain disabled until reviewed.",
        ]
        warnings.extend(self._dependency_warnings(descriptor))
        actions = [
            f"validate {source}",
            f"copy package folder to {target}",
            f"create plugin-data directory {descriptor.data_dir}",
        ]
        if target.exists():
            raise ValueError(f"plugin already exists in installed packages: {plugin_id}")
        if self._plugin_exists_elsewhere(plugin_id):
            raise ValueError(f"plugin id already exists in plugin package roots: {plugin_id}")
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, target, symlinks=False)
            installed_descriptor = PluginPackageScanner(
                plugin_root=self.plugin_root,
                data_root=self.data_root,
                source_dirs={"installed": "installed"},
            ).scan().by_plugin_id().get(plugin_id)
            if installed_descriptor is None or not installed_descriptor.valid:
                if target.exists():
                    shutil.rmtree(target)
                message = "; ".join(installed_descriptor.errors) if installed_descriptor else "installed package not found after copy"
                raise ValueError(message)
            descriptor = installed_descriptor
            PluginDataService(data_root=self.data_root).ensure_for_descriptor(descriptor)
            integrity = build_package_integrity(target)
        return PluginPackageImportResult(
            plugin_id=plugin_id,
            status="validated" if dry_run else "installed",
            dry_run=dry_run,
            source_path=str(source),
            target_path=str(target),
            data_dir=str(descriptor.data_dir),
            descriptor=descriptor,
            integrity=integrity,
            actions=actions,
            warnings=warnings,
        )

    def _import_archive(self, archive_path: Path, *, dry_run: bool) -> PluginPackageImportResult:
        if archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("plugin archive exceeds maximum supported size")
        with tempfile.TemporaryDirectory(prefix="lambchat-plugin-import-") as temp_dir:
            staging_root = Path(temp_dir).resolve()
            _extract_archive_safely(archive_path, staging_root)
            source = _find_single_plugin_folder(staging_root)
            result = self.import_folder(source, dry_run=dry_run)
            return PluginPackageImportResult(
                plugin_id=result.plugin_id,
                status=result.status,
                dry_run=result.dry_run,
                source_path=str(archive_path),
                target_path=result.target_path,
                data_dir=result.data_dir,
                descriptor=result.descriptor,
                integrity=result.integrity,
                actions=[f"extract archive {archive_path}", *result.actions],
                warnings=result.warnings,
            )

    def _validate_source(self, source: Path) -> PluginFolderDescriptor:
        if not source.exists() or not source.is_dir():
            raise ValueError("source_path must be an existing local plugin directory")
        if source.is_symlink():
            raise ValueError("plugin source folder symlinks are not allowed")
        _validate_package_tree(source)
        scan_root = source.parent
        scan = PluginPackageScanner(
            plugin_root=scan_root.parent,
            data_root=self.data_root,
            source_dirs={"staged": scan_root.name},
        ).scan()
        descriptor = next((item for item in scan.descriptors if item.folder == source), None)
        if descriptor is None:
            raise ValueError("source_path does not contain a plugin package")
        if not descriptor.valid:
            raise ValueError("; ".join(descriptor.errors) or "plugin package is invalid")
        return descriptor

    def _plugin_exists_elsewhere(self, plugin_id: str) -> bool:
        scan = PluginPackageScanner(plugin_root=self.plugin_root, data_root=self.data_root).scan()
        return plugin_id in scan.by_plugin_id()

    def _dependency_warnings(self, descriptor: PluginFolderDescriptor) -> list[str]:
        manifest = descriptor.manifest
        if manifest is None or not manifest.depends_on:
            return []
        scan = PluginPackageScanner(plugin_root=self.plugin_root, data_root=self.data_root).scan()
        available = set(scan.by_plugin_id()) | {"skill_core"}
        missing = [dependency for dependency in manifest.depends_on if dependency not in available]
        if not missing:
            return []
        return [
            "Missing plugin dependencies before install: " + ", ".join(missing),
        ]

    def _ensure_inside(self, path: Path, root: Path) -> None:
        try:
            path.resolve().relative_to(root.resolve())
        except ValueError as exc:
            raise ValueError("plugin import target escapes installed root") from exc


def _is_supported_archive(path: Path) -> bool:
    lower_name = path.name.lower()
    return any(lower_name.endswith(suffix) for suffix in SUPPORTED_ARCHIVE_SUFFIXES)


def _extract_archive_safely(archive_path: Path, target_root: Path) -> None:
    lower_name = archive_path.name.lower()
    if lower_name.endswith(".zip"):
        _extract_zip_safely(archive_path, target_root)
        return
    if lower_name.endswith((".tar", ".tar.gz", ".tgz")):
        _extract_tar_safely(archive_path, target_root)
        return
    raise ValueError("unsupported plugin archive type")


def _extract_zip_safely(archive_path: Path, target_root: Path) -> None:
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError("plugin archive contains too many files")
        for member in members:
            if member.is_dir():
                destination = _safe_archive_destination(target_root, member.filename)
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if member.file_size > MAX_ARCHIVE_BYTES:
                raise ValueError("plugin archive member exceeds maximum supported size")
            destination = _safe_archive_destination(target_root, member.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)


def _extract_tar_safely(archive_path: Path, target_root: Path) -> None:
    with tarfile.open(archive_path) as archive:
        members = archive.getmembers()
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError("plugin archive contains too many files")
        for member in members:
            if member.issym() or member.islnk() or member.isdev():
                raise ValueError("plugin archive links and device files are not allowed")
            destination = _safe_archive_destination(target_root, member.name)
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            if member.size > MAX_ARCHIVE_BYTES:
                raise ValueError("plugin archive member exceeds maximum supported size")
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            with source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)


def _safe_archive_destination(target_root: Path, member_name: str) -> Path:
    normalized = member_name.replace("\\", "/").strip()
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("plugin archive contains an unsafe path")
    destination = (target_root / normalized).resolve()
    try:
        destination.relative_to(target_root)
    except ValueError as exc:
        raise ValueError("plugin archive path escapes staging directory") from exc
    return destination


def _validate_package_tree(source: Path) -> None:
    file_count = 0
    total_bytes = 0
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError("plugin package symlinks are not allowed")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("plugin package contains unsupported filesystem entries")
        file_count += 1
        if file_count > MAX_PACKAGE_FILES:
            raise ValueError("plugin package contains too many files")
        total_bytes += path.stat().st_size
        if total_bytes > MAX_PACKAGE_BYTES:
            raise ValueError("plugin package exceeds maximum supported size")


def _find_single_plugin_folder(staging_root: Path) -> Path:
    candidates = [path for path in staging_root.iterdir() if path.is_dir() and (path / "plugin.yaml").is_file()]
    if len(candidates) != 1:
        raise ValueError("plugin archive must contain exactly one plugin folder with plugin.yaml")
    return candidates[0]
