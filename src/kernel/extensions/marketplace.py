"""Marketplace-facing extension entry models.

These models describe the Extension Marketplace list/detail shape without
replacing legacy Skill marketplace payloads. Unknown future extension types are
kept as data so basic marketplace listings can survive before core support is
implemented for that type.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.kernel.extensions.manifest import (
    ExtensionCompatibility,
    ExtensionManifest,
    ExtensionType,
    InstallState,
)


def _dedupe_non_blank_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


class ExtensionMarketplaceEntry(BaseModel):
    """Common Extension Marketplace item shape.

    `type` intentionally remains a string instead of `ExtensionType` so future
    marketplace sources can be listed safely before the app knows how to install
    or run that extension type.
    """

    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1)
    type: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = Field("1.0.0", min_length=1)
    publisher: str = "unknown"
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    install_state: InstallState = InstallState.NOT_INSTALLED
    enabled: bool = True
    compatibility: ExtensionCompatibility = Field(default_factory=ExtensionCompatibility)
    legacy: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id", "type", "name", "version", "publisher")
    @classmethod
    def normalize_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("marketplace extension fields cannot be blank")
        return normalized

    @field_validator("tags", "capabilities", "permissions")
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)

    @property
    def known_type(self) -> ExtensionType | None:
        """Return the known ExtensionType, or None for future marketplace types."""
        try:
            return ExtensionType(self.type)
        except ValueError:
            return None

    def as_manifest(self) -> ExtensionManifest | None:
        """Convert known marketplace entries into installable extension manifests.

        Unknown future types intentionally return None so callers can keep
        listing them without pretending the current runtime can install them.
        """
        known_type = self.known_type
        if known_type is None:
            return None
        return ExtensionManifest(
            id=self.id,
            type=known_type,
            name=self.name,
            version=self.version,
            publisher=self.publisher,
            description=self.description,
            tags=self.tags,
            capabilities=self.capabilities,
            permissions=self.permissions,
            install_state=self.install_state,
            enabled=self.enabled,
            compatibility=self.compatibility,
        )

    @property
    def uses_plugin_runtime(self) -> bool:
        """Whether this Extension Center item enters Plugin Runtime lifecycle."""
        return self.known_type is ExtensionType.PLUGIN


def extension_uses_plugin_runtime(extension: ExtensionManifest | ExtensionMarketplaceEntry) -> bool:
    """Return True only for business plugin extensions.

    Skill and MCP entries remain Extension Center items handled by their core
    services; they do not enter Plugin Runtime route/tool/hook lifecycle.
    """
    extension_type = extension.type
    if isinstance(extension_type, ExtensionType):
        return extension_type is ExtensionType.PLUGIN
    return extension_type == ExtensionType.PLUGIN.value


def build_skill_marketplace_entry(
    *,
    skill_name: str,
    description: str = "",
    tags: list[str] | None = None,
    version: str = "1.0.0",
    publisher: str | None = None,
    enabled: bool = True,
    file_count: int = 0,
) -> ExtensionMarketplaceEntry:
    """Expose a legacy Skill marketplace record through the extension shape."""
    return ExtensionMarketplaceEntry(
        id=f"skill:{skill_name}",
        type=ExtensionType.SKILL.value,
        name=skill_name,
        version=version or "1.0.0",
        publisher=publisher or "unknown",
        description=description,
        tags=tags or [],
        capabilities=["skill"],
        install_state=InstallState.NOT_INSTALLED,
        enabled=enabled,
        legacy={
            "kind": "marketplace_skill",
            "skill_name": skill_name,
            "file_count": file_count,
        },
    )
