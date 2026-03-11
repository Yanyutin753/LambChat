"""Configuration management using pydantic-settings.

This module provides centralized configuration management for the application.
"""

from .base import Settings, get_settings, settings
from .constants import (
    JWT_SECRET_KEY_MIN_LENGTH,
    RESTART_REQUIRED_SETTINGS,
    SENSITIVE_SETTINGS,
)
from .definitions import SETTING_DEFINITIONS
from .service import initialize_settings, refresh_settings

__all__ = [
    # Settings class and instance
    "Settings",
    "get_settings",
    "settings",
    # Definitions
    "SETTING_DEFINITIONS",
    # Constants
    "JWT_SECRET_KEY_MIN_LENGTH",
    "RESTART_REQUIRED_SETTINGS",
    "SENSITIVE_SETTINGS",
    # Service functions
    "initialize_settings",
    "refresh_settings",
]
