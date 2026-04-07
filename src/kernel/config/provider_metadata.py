"""
Provider metadata for UI display.

This module provides UI-specific metadata (icon, color, website, description)
for LLM providers. It derives from the Provider Registry's ui_meta field,
so the single source of truth is the provider class definition.

The ProviderRegistry.get_all_provider_ui_metas() method returns
ProviderUIMeta objects populated from each provider's ui_meta field.
"""

from dataclasses import dataclass
from typing import Optional

from src.infra.llm.providers.registry import (
    ProviderRegistry,
)


@dataclass
class ProviderMeta:
    """UI metadata for a provider."""

    name: str  # Provider identifier (e.g., "openai", "anthropic")
    display_name: str  # Human-readable name
    icon: str  # Icon class or emoji
    color: str  # Brand color (hex)
    website: str  # Official website
    description: str  # Short description


# Cache for provider metas (derived from registry on first access)
_provider_meta_cache: Optional[list[ProviderMeta]] = None


def _build_provider_metas() -> list[ProviderMeta]:
    """Build ProviderMeta list from registry."""
    registry = ProviderRegistry.get_instance()
    metas = []
    for name in registry.list_providers():
        instance = registry.get_provider(name)
        if not instance:
            continue
        ui_meta = instance.get_ui_meta()
        metas.append(
            ProviderMeta(
                name=name,
                display_name=instance.display_name,
                icon=ui_meta.icon or name,
                color=ui_meta.color or "#888888",
                website=ui_meta.website,
                description=ui_meta.description,
            )
        )
    return metas


def get_provider_meta(name: str) -> Optional[ProviderMeta]:
    """Get UI metadata for a provider by name."""
    global _provider_meta_cache
    if _provider_meta_cache is None:
        _provider_meta_cache = _build_provider_metas()
    for meta in _provider_meta_cache:
        if meta.name == name:
            return meta
    return None


def get_all_provider_metas() -> list[ProviderMeta]:
    """Get all provider metadata."""
    global _provider_meta_cache
    if _provider_meta_cache is None:
        _provider_meta_cache = _build_provider_metas()
    return _provider_meta_cache


def invalidate_provider_meta_cache() -> None:
    """Clear the cached provider metas (call after provider registration changes)."""
    global _provider_meta_cache
    _provider_meta_cache = None
