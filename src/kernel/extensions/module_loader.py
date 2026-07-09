"""Controlled module loading for trusted plugin backend contributions."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from src.kernel.extensions.manifest import PluginInstallType, PluginManifest


def split_module_ref(module_ref: str) -> tuple[str, str | None]:
    module_name, separator, attr_name = module_ref.partition(":")
    return module_name, attr_name if separator else None


def is_plugin_relative_module_ref(module_ref: str) -> bool:
    module_name, _ = split_module_ref(module_ref)
    normalized = module_name.replace("\\", "/")
    return normalized.startswith("./") or normalized.startswith("../")


def load_plugin_module(manifest: PluginManifest, module_ref: str) -> ModuleType:
    module_name, _ = split_module_ref(module_ref)
    if is_plugin_relative_module_ref(module_ref):
        return _load_plugin_relative_module(manifest, module_name)
    return importlib.import_module(module_name)


def load_plugin_attr(
    manifest: PluginManifest,
    module_ref: str,
    *,
    default_attr: str | None = None,
) -> Any:
    module_name, attr_name = split_module_ref(module_ref)
    module = (
        _load_plugin_relative_module(manifest, module_name)
        if is_plugin_relative_module_ref(module_ref)
        else importlib.import_module(module_name)
    )
    resolved_attr = attr_name or default_attr
    return getattr(module, resolved_attr) if resolved_attr else module


def validate_plugin_relative_module_ref(manifest: PluginManifest, module_ref: str) -> None:
    module_name, _ = split_module_ref(module_ref)
    if is_plugin_relative_module_ref(module_ref):
        _plugin_relative_file(manifest, module_name)


def _load_plugin_relative_module(manifest: PluginManifest, module_name: str) -> ModuleType:
    module_file = _plugin_relative_file(manifest, module_name)
    synthetic_name = _synthetic_module_name(manifest.id, module_file)
    cached = sys.modules.get(synthetic_name)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(synthetic_name, module_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load plugin module: {manifest.id}:{module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[synthetic_name] = module
    spec.loader.exec_module(module)
    return module


def _plugin_relative_file(manifest: PluginManifest, module_name: str) -> Path:
    if manifest.install_type is not PluginInstallType.SYSTEM_BUILTIN:
        raise ValueError(f"plugin-relative backend modules are trusted-system only: {manifest.id}")
    if not manifest.package_source_path:
        raise ValueError(f"plugin package path is required for relative module: {manifest.id}")
    plugin_root = Path(manifest.package_source_path).resolve()
    normalized = module_name.replace("\\", "/")
    if not normalized.startswith("./"):
        raise ValueError(f"plugin module must be relative to the plugin root: {module_name}")
    if not normalized.endswith(".py"):
        raise ValueError(f"plugin module must reference a Python file: {module_name}")
    module_file = (plugin_root / normalized[2:]).resolve()
    try:
        module_file.relative_to(plugin_root)
    except ValueError as exc:
        raise ValueError(f"plugin module escapes plugin root: {module_name}") from exc
    if not module_file.is_file():
        raise ImportError(f"plugin module file not found: {module_name}")
    return module_file


def _synthetic_module_name(plugin_id: str, module_file: Path) -> str:
    digest = hashlib.sha1(str(module_file).encode("utf-8")).hexdigest()[:16]
    safe_plugin_id = plugin_id.replace("-", "_").replace(".", "_")
    return f"_lambchat_plugin_{safe_plugin_id}_{digest}"
