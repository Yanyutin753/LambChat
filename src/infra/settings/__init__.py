"""
Settings infrastructure module

This module provides database-first settings with .env fallback.
All setting definitions are in src.kernel.config for single source of truth.
"""

from src.infra.settings.service import SettingsService, get_settings_service
from src.infra.settings.storage import SettingsStorage

# Re-export constants from config.py for backward compatibility
from src.kernel.config import (
    RESTART_REQUIRED_SETTINGS,
    SENSITIVE_SETTINGS,
    SETTING_DEFINITIONS,
)

__all__ = [
    "SettingsService",
    "SettingsStorage",
    "get_settings_service",
    "RESTART_REQUIRED_SETTINGS",
    "SENSITIVE_SETTINGS",
    "SETTING_DEFINITIONS",
]
