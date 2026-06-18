"""In-memory registries for extension and plugin manifests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import List, Literal

from src.kernel.extensions.manifest import (
    ExtensionManifest,
    ExtensionType,
    PluginLifecycleHook,
    PluginManifest,
    PluginRoute,
    PluginTool,
)

LifecyclePhase = Literal["startup", "shutdown"]


class RegistryDuplicateError(ValueError):
    """Raised when a registry receives the same manifest id twice."""


@dataclass(frozen=True)
class PluginLifecycleHookRegistration:
    """A lifecycle hook declaration with registry ordering metadata."""

    plugin_id: str
    hook: PluginLifecycleHook
    plugin_index: int
    hook_index: int

    @property
    def name(self) -> str:
        return self.hook.name

    @property
    def module(self) -> str:
        return self.hook.module

    @property
    def phase(self) -> LifecyclePhase:
        return self.hook.phase

    @property
    def order(self) -> int:
        return self.hook.order


@dataclass(frozen=True)
class PluginRouteRegistration:
    """A backend route declaration with plugin ownership metadata."""

    plugin_id: str
    route: PluginRoute

    @property
    def name(self) -> str:
        return self.route.name

    @property
    def prefix(self) -> str:
        return self.route.prefix

    @property
    def module(self) -> str:
        return self.route.module

    @property
    def required_permissions(self) -> list[str]:
        return self.route.required_permissions

    @property
    def tags(self) -> list[str]:
        return self.route.tags


@dataclass(frozen=True)
class PluginToolRegistration:
    """A tool declaration with plugin ownership metadata."""

    plugin_id: str
    tool: PluginTool

    @property
    def name(self) -> str:
        return self.tool.name

    @property
    def module(self) -> str:
        return self.tool.module

    @property
    def required_permissions(self) -> list[str]:
        return self.tool.required_permissions

    @property
    def legacy_ids(self) -> list[str]:
        return self.tool.legacy_ids


class ExtensionRegistry:
    """Build-time registry for all extension manifests."""

    def __init__(self, manifests: Iterable[ExtensionManifest] | None = None) -> None:
        self._items: dict[str, ExtensionManifest] = {}
        if manifests:
            for manifest in manifests:
                self.register(manifest)

    def register(self, manifest: ExtensionManifest) -> ExtensionManifest:
        if manifest.id in self._items:
            raise RegistryDuplicateError(f"extension already registered: {manifest.id}")
        self._items[manifest.id] = manifest
        return manifest

    def get(self, extension_id: str) -> ExtensionManifest | None:
        return self._items.get(extension_id)

    def list(
        self,
        *,
        extension_type: ExtensionType | str | None = None,
        enabled: bool | None = None,
    ) -> list[ExtensionManifest]:
        items = list(self._items.values())
        if extension_type is not None:
            expected = ExtensionType(extension_type)
            items = [item for item in items if item.type == expected]
        if enabled is not None:
            items = [item for item in items if item.enabled is enabled]
        return items

    def permissions(self, *, enabled_only: bool = True) -> List[str]:
        seen: set[str] = set()
        result: List[str] = []
        for manifest in self._items.values():
            if enabled_only and not manifest.enabled:
                continue
            for permission in manifest.permissions:
                if permission not in seen:
                    seen.add(permission)
                    result.append(permission)
        return result

class PluginRegistry:
    """Build-time registry for plugin manifests."""

    def __init__(self, manifests: Iterable[PluginManifest] | None = None) -> None:
        self._items: dict[str, PluginManifest] = {}
        if manifests:
            for manifest in manifests:
                self.register(manifest)

    def register(self, manifest: PluginManifest) -> PluginManifest:
        if manifest.id in self._items:
            raise RegistryDuplicateError(f"plugin already registered: {manifest.id}")
        self._items[manifest.id] = manifest
        return manifest

    def get(self, plugin_id: str) -> PluginManifest | None:
        return self._items.get(plugin_id)

    def list(self, *, enabled_by_default: bool | None = None) -> list[PluginManifest]:
        items = list(self._items.values())
        if enabled_by_default is not None:
            items = [item for item in items if item.enabled_by_default is enabled_by_default]
        return items

    def as_extension_registry(self, *, publisher: str = "core") -> ExtensionRegistry:
        return ExtensionRegistry(
            manifest.as_extension_manifest(publisher=publisher) for manifest in self._items.values()
        )

    def permissions(self, *, enabled_only: bool = True) -> List[str]:
        seen: set[str] = set()
        result: List[str] = []
        for manifest in self._items.values():
            if enabled_only and not manifest.enabled_by_default:
                continue
            for permission in manifest.declared_permissions():
                if permission not in seen:
                    seen.add(permission)
                    result.append(permission)
        return result

    def routes(self, *, enabled_only: bool = True) -> List[PluginRouteRegistration]:
        registrations: List[PluginRouteRegistration] = []
        for manifest in self._items.values():
            if enabled_only and not manifest.enabled_by_default:
                continue
            for route in manifest.routers:
                registrations.append(
                    PluginRouteRegistration(plugin_id=manifest.id, route=route)
                )
        return registrations

    def tools(self, *, enabled_only: bool = True) -> List[PluginToolRegistration]:
        registrations: List[PluginToolRegistration] = []
        for manifest in self._items.values():
            if enabled_only and not manifest.enabled_by_default:
                continue
            for tool in manifest.tools:
                registrations.append(
                    PluginToolRegistration(plugin_id=manifest.id, tool=tool)
                )
        return registrations

    def lifecycle_hooks(
        self,
        *,
        phase: LifecyclePhase | None = None,
        enabled_only: bool = True,
    ) -> List[PluginLifecycleHookRegistration]:
        """Return lifecycle hook declarations in stable execution order.

        This method only collects declarations. It intentionally does not import
        hook modules or execute hook callables; the future execution layer must
        isolate import/runtime errors so core startup and shutdown are not blocked.
        """
        registrations: List[PluginLifecycleHookRegistration] = []
        for plugin_index, manifest in enumerate(self._items.values()):
            if enabled_only and not manifest.enabled_by_default:
                continue
            for hook_index, hook in enumerate(manifest.lifespan_hooks):
                if phase is not None and hook.phase != phase:
                    continue
                registrations.append(
                    PluginLifecycleHookRegistration(
                        plugin_id=manifest.id,
                        hook=hook,
                        plugin_index=plugin_index,
                        hook_index=hook_index,
                    )
                )
        return sorted(
            registrations,
            key=lambda item: (item.order, item.plugin_index, item.hook_index),
        )
