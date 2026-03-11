"""Configuration management using pydantic-settings.

This module re-exports all public API from src.kernel.config package for backward compatibility.
"""

from src.kernel.config import (
    JWT_SECRET_KEY_MIN_LENGTH,
    RESTART_REQUIRED_SETTINGS,
    SENSITIVE_SETTINGS,
    SETTING_DEFINITIONS,
    Settings,
    get_settings,
    initialize_settings,
    refresh_settings,
    settings,
)

__all__ = [
    "Settings",
    "get_settings",
    "settings",
    "SETTING_DEFINITIONS",
    "JWT_SECRET_KEY_MIN_LENGTH",
    "RESTART_REQUIRED_SETTINGS",
    "SENSITIVE_SETTINGS",
    "initialize_settings",
    "refresh_settings",
]
