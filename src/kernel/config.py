"""Configuration management using pydantic-settings."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.infra.settings.service import SettingsService
    from src.infra.storage.s3 import S3Config

import logging
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic_settings import BaseSettings

from src.kernel.schemas.setting import SettingCategory, SettingType

logger = logging.getLogger(__name__)
# Project root directory (where pyproject.toml is)
PROJECT_ROOT = Path(__file__).parent.parent.parent


# ============================================
# Settings that require server restart to take effect
# ============================================
RESTART_REQUIRED_SETTINGS = {
    "HOST",
    "PORT",
    "MONGODB_URL",
    "MONGODB_DB",
    "MONGODB_ENABLED",
    "REDIS_URL",
    "REDIS_PASSWORD",
    "JWT_SECRET_KEY",
}

# ============================================
# Sensitive settings - values hidden in API responses
# ============================================
SENSITIVE_SETTINGS = {
    "LLM_API_KEY",
    "ANTHROPIC_API_KEY",
    "JWT_SECRET_KEY",
    "MONGODB_URL",
    "MONGODB_PASSWORD",
    "REDIS_URL",
    "REDIS_PASSWORD",
    "LANGSMITH_API_KEY",
    "EMBEDDING_API_KEY",
    "RERANK_API_KEY",
    "MILVUS_PASSWORD",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
}

# ============================================
# Setting metadata definitions - single source of truth
# ============================================
SETTING_DEFINITIONS: dict[str, dict] = {
    # ============================================
    # Frontend Settings
    # ============================================
    "DEFAULT_AGENT": {
        "type": SettingType.STRING,
        "category": SettingCategory.FRONTEND,
        "description": "Default agent type for new sessions",
        "default": "default",
        "frontend_visible": True,
    },
    "WELCOME_SUGGESTIONS": {
        "type": SettingType.JSON,
        "category": SettingCategory.FRONTEND,
        "description": "Welcome page suggestions displayed to users (JSON array with icon and text)",
        "default": [
            {"icon": "🐍", "text": "Create a Python hello world script"},
            {"icon": "📁", "text": "List files in the workspace directory"},
            {"icon": "📄", "text": "Read the README.md file"},
            {"icon": "🔧", "text": "Help me write a shell script"},
        ],
        "frontend_visible": True,
    },
    # ============================================
    # Application Settings
    # ============================================
    "DEBUG": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.AGENT,
        "description": "Enable debug mode",
        "default": False,
    },
    "LOG_LEVEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.AGENT,
        "description": "Logging level (DEBUG, INFO, WARNING, ERROR)",
        "default": "INFO",
    },
    # ============================================
    # LLM Settings
    # ============================================
    "LLM_MODEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.LLM,
        "description": "LLM model identifier (e.g., anthropic/claude-3-5-sonnet)",
        "default": "anthropic/claude-3-5-sonnet-20241022",
    },
    "LLM_TEMPERATURE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "description": "LLM temperature for response generation (0.0-2.0)",
        "default": 0.7,
    },
    "LLM_MAX_TOKENS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "description": "Maximum tokens in LLM response",
        "default": 4096,
    },
    "LLM_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.LLM,
        "description": "LLM API key",
        "default": "",
    },
    "LLM_API_BASE": {
        "type": SettingType.STRING,
        "category": SettingCategory.LLM,
        "description": "LLM API base URL",
        "default": "",
    },
    "ANTHROPIC_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.LLM,
        "description": "Anthropic API key (for LangChain)",
        "default": "",
    },
    "ANTHROPIC_BASE_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.LLM,
        "description": "Anthropic API base URL",
        "default": "",
    },
    # ============================================
    # Session Settings
    # ============================================
    "SESSION_BACKEND": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "Session storage backend (redis, postgres)",
        "default": "redis",
    },
    "SESSION_MAX_AGE_DAYS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "description": "Maximum session age in days",
        "default": 7,
    },
    "SESSION_MAX_RUNS_PER_SESSION": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "description": "Maximum runs per session",
        "default": 100,
    },
    "ENABLE_MESSAGE_HISTORY": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SESSION,
        "description": "Enable message history storage",
        "default": True,
    },
    "SSE_CACHE_TTL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "description": "Redis TTL for SSE events in seconds",
        "default": 3600,
    },
    "MAX_EVENTS_PER_SESSION": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "description": "Maximum events to store per session",
        "default": 10000,
    },
    "SESSION_TITLE_MODEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "LLM model for generating session titles (e.g., gpt-4o-mini, claude-3-haiku)",
        "default": "claude-3-5-haiku-20241022",
        "frontend_visible": False,
    },
    "SESSION_TITLE_PROMPT": {
        "type": SettingType.TEXT,
        "category": SettingCategory.SESSION,
        "description": "Prompt template for generating session titles. Use {message} as placeholder for user message.",
        "default": "Generate a short title (max 10 words) for this conversation based on the user message:\n\n{message}",
        "frontend_visible": False,
    },
    # ============================================
    # Feature Flags
    # ============================================
    "ENABLE_MCP": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.FEATURES,
        "description": "Enable MCP integration",
        "default": False,
    },
    "ENABLE_SKILLS": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.FEATURES,
        "description": "Enable skills feature",
        "default": True,
    },
    # ============================================
    # Sandbox Settings
    # ============================================
    "SANDBOX_PLATFORM": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Sandbox platform: runloop, daytona, or modal",
        "default": "runloop",
    },
    "RUNLOOP_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Runloop API Key",
        "default": "",
    },
    "RUNLOOP_BASE_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Runloop API Base URL",
        "default": "https://api.runloop.ai",
    },
    "DAYTONA_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona API Key",
        "default": "",
    },
    "DAYTONA_SERVER_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona Server URL",
        "default": "",
    },
    "DAYTONA_TIMEOUT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona command timeout in seconds",
        "default": 180,
    },
    "MODAL_APP_NAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Modal App Name",
        "default": "",
    },
    # ============================================
    # Skills Settings
    # ============================================
    "SKILLS_MONGODB_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.FEATURES,
        "description": "Use MongoDB for skills storage",
        "default": False,
    },
    # ============================================
    # Database Settings (MongoDB)
    # ============================================
    "MONGODB_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "MongoDB connection URL",
        "default": "mongodb://localhost:27017",
    },
    "MONGODB_DB": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "MongoDB database name",
        "default": "agent_state",
    },
    "MONGODB_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SESSION,
        "description": "Enable MongoDB for state persistence",
        "default": True,
    },
    "MONGODB_USERNAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "MongoDB username",
        "default": "",
    },
    "MONGODB_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "MongoDB password",
        "default": "",
    },
    "MONGODB_AUTH_SOURCE": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "MongoDB authentication database",
        "default": "admin",
    },
    # ============================================
    # Redis Settings
    # ============================================
    "REDIS_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "Redis connection URL",
        "default": "redis://localhost:6379/0",
    },
    "REDIS_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "Redis password",
        "default": "",
    },
    # ============================================
    # LangSmith Tracing Settings
    # ============================================
    "LANGSMITH_TRACING": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.TRACING,
        "description": "Enable LangSmith tracing",
        "default": False,
    },
    "LANGSMITH_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "description": "LangSmith API key",
        "default": "",
    },
    "LANGSMITH_PROJECT": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "description": "LangSmith project name",
        "default": "lamb-agent",
    },
    "LANGSMITH_API_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "description": "LangSmith API URL",
        "default": "https://api.smith.langchain.com",
    },
    "LANGSMITH_SAMPLE_RATE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.TRACING,
        "description": "LangSmith sample rate (0.0-1.0)",
        "default": 1.0,
    },
    # ============================================
    # JWT Authentication Settings
    # ============================================
    "JWT_SECRET_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SECURITY,
        "description": "JWT secret key for token signing",
        "default": "your-secret-key-change-in-production",
    },
    "JWT_ALGORITHM": {
        "type": SettingType.STRING,
        "category": SettingCategory.SECURITY,
        "description": "JWT signing algorithm",
        "default": "HS256",
    },
    "ACCESS_TOKEN_EXPIRE_HOURS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SECURITY,
        "description": "Access token expiration in hours",
        "default": 24,
    },
    "REFRESH_TOKEN_EXPIRE_DAYS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SECURITY,
        "description": "Refresh token expiration in days",
        "default": 7,
    },
    # ============================================
    # S3 Storage Settings
    # ============================================
    "S3_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.S3,
        "description": "Enable S3-compatible storage for file uploads",
        "default": False,
    },
    "S3_PROVIDER": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 provider: aws, aliyun, tencent, minio, custom",
        "default": "aws",
    },
    "S3_ENDPOINT_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 endpoint URL (required for MinIO and custom providers)",
        "default": "",
    },
    "S3_ACCESS_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 access key",
        "default": "",
    },
    "S3_SECRET_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 secret key",
        "default": "",
    },
    "S3_REGION": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 region",
        "default": "us-east-1",
    },
    "S3_BUCKET_NAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 bucket name",
        "default": "",
    },
    "S3_CUSTOM_DOMAIN": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "Custom CDN domain for S3 files",
        "default": "",
    },
    "S3_PATH_STYLE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.S3,
        "description": "Use path-style URLs (required for MinIO)",
        "default": False,
    },
    "S3_MAX_FILE_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "Maximum file size in bytes (default: 10MB)",
        "default": 10485760,
    },
    "S3_PUBLIC_BUCKET": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.S3,
        "description": "Whether the S3 bucket is publicly readable",
        "default": False,
    },
    "S3_PRESIGNED_URL_EXPIRES": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "Presigned URL expiration time in seconds (default: 7 days)",
        "default": 604800,
    },
    # ============================================
    # User Management Settings
    # ============================================
    "DEFAULT_USER_ROLE": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "Default role for newly registered users",
        "default": "user",
        "frontend_visible": True,
    },
}


def _get_default_from_settings(key: str) -> Any:
    """Get default value from SETTING_DEFINITIONS"""
    if key in SETTING_DEFINITIONS:
        return SETTING_DEFINITIONS[key].get("default")
    return None


def _get_git_info() -> tuple[str | None, str | None]:
    """Get git tag and commit hash at startup.

    Returns:
        tuple of (git_tag, commit_hash) or (None, None) if not in a git repo
    """
    try:
        # Get git describe (tag or commit)
        result = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        describe = result.stdout.strip() if result.returncode == 0 else None

        # Get commit hash
        hash_result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=PROJECT_ROOT,
        )
        commit_hash = (
            hash_result.stdout.strip() if hash_result.returncode == 0 else None
        )

        # If describe looks like a tag (starts with v), use it as tag
        git_tag = describe if describe and describe.startswith("v") else None

        return git_tag, commit_hash
    except Exception:
        return None, None


# Get git info at module load time
_GIT_TAG, _COMMIT_HASH = _get_git_info()


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Default values are defined in SETTING_DEFINITIONS (single source of truth).
    This class uses pydantic-settings to load from .env and environment variables.
    Runtime values can be updated from database via initialize_settings().
    """

    # Application (not in SETTING_DEFINITIONS - internal use only)
    APP_NAME: str = "LambChat"
    APP_VERSION: str = "1.0.0"

    # Version Info (populated at startup)
    GIT_TAG: Optional[str] = None
    COMMIT_HASH: Optional[str] = None
    BUILD_TIME: Optional[str] = None

    # Logging Configuration (not in SETTING_DEFINITIONS - internal use only)
    LOG_LEVELS: str = ""
    LOG_FORMAT: str = (
        "%(asctime)s.%(msecs)03d [%(levelname)s] [%(trace_info)s] %(name)s - %(message)s"
    )
    LOG_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

    # Session Configuration (not in SETTING_DEFINITIONS)
    SESSION_MAX_MESSAGES: int = 20

    # ============================================
    # All settings below get defaults from SETTING_DEFINITIONS
    # ============================================

    # Application Settings
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    # LLM Settings
    LLM_API_KEY: str = ""
    LLM_API_BASE: Optional[str] = None
    LLM_MODEL: str = "anthropic/claude-3-5-sonnet-20241022"
    LLM_TEMPERATURE: float = 0.7
    LLM_MAX_TOKENS: int = 4096
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: Optional[str] = None

    # Feature Flags
    ENABLE_MCP: bool = False
    ENABLE_SKILLS: bool = True

    # Session Settings
    SESSION_BACKEND: str = "redis"
    SESSION_MAX_AGE_DAYS: int = 7
    SESSION_MAX_RUNS_PER_SESSION: int = 100
    ENABLE_MESSAGE_HISTORY: bool = True
    SSE_CACHE_TTL: int = 3600
    MAX_EVENTS_PER_SESSION: int = 10000
    SESSION_TITLE_MODEL: str = "claude-3-5-haiku-20241022"
    SESSION_TITLE_PROMPT: str = (
        "Generate a short title (max 10 words) for this conversation."
    )

    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None

    # MongoDB Settings
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "agent_state"
    MONGODB_ENABLED: bool = True
    MONGODB_USERNAME: str = ""
    MONGODB_PASSWORD: str = ""
    MONGODB_AUTH_SOURCE: str = "admin"

    MONGODB_SESSIONS_COLLECTION: str = "sessions"
    MONGODB_TRACES_COLLECTION: str = "traces"

    # Sandbox Settings
    SANDBOX_PLATFORM: str = "runloop"  # runloop, daytona, modal
    RUNLOOP_API_KEY: str = ""
    RUNLOOP_BASE_URL: str = "https://api.runloop.ai"
    DAYTONA_API_KEY: str = ""
    DAYTONA_SERVER_URL: str = ""
    DAYTONA_TIMEOUT: int = 180  # 3 minutes
    MODAL_APP_NAME: str = ""

    # Skills Settings
    SKILLS_MONGODB_ENABLED: bool = False

    # LangSmith Tracing Settings
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "lamb-agent"
    LANGSMITH_API_URL: str = "https://api.smith.langchain.com"
    LANGSMITH_SAMPLE_RATE: float = 1.0

    # JWT Authentication Settings
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS: int = 24
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # S3 Storage Settings
    S3_ENABLED: bool = False
    S3_PROVIDER: str = "aws"
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = ""
    S3_CUSTOM_DOMAIN: Optional[str] = None
    S3_PATH_STYLE: bool = False
    S3_MAX_FILE_SIZE: int = 10 * 1024 * 1024
    S3_PUBLIC_BUCKET: bool = False
    S3_PRESIGNED_URL_EXPIRES: int = 7 * 24 * 3600  # 7 days

    # Frontend Settings
    DEFAULT_AGENT: str = "default"
    WELCOME_SUGGESTIONS: list = [
        {"icon": "🐍", "text": "Create a Python hello world script"},
        {"icon": "📁", "text": "List files in the workspace directory"},
        {"icon": "📄", "text": "Read the README.md file"},
        {"icon": "🔧", "text": "Help me write a shell script"},
    ]
    DEFAULT_USER_ROLE: str = "user"

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # Set version info from git (if not already set via env)
        if self.GIT_TAG is None:
            self.GIT_TAG = _GIT_TAG
        if self.COMMIT_HASH is None:
            self.COMMIT_HASH = _COMMIT_HASH
        if self.BUILD_TIME is None:
            self.BUILD_TIME = os.environ.get("BUILD_TIME")

        # Sync LangSmith settings to os.environ (required by langsmith SDK)
        if self.LANGSMITH_TRACING:
            os.environ["LANGSMITH_TRACING"] = "true"
        if self.LANGSMITH_API_KEY:
            os.environ["LANGSMITH_API_KEY"] = self.LANGSMITH_API_KEY
        if self.LANGSMITH_PROJECT:
            os.environ["LANGSMITH_PROJECT"] = self.LANGSMITH_PROJECT
        if self.LANGSMITH_API_URL:
            os.environ["LANGSMITH_API_URL"] = self.LANGSMITH_API_URL
        if self.LANGSMITH_SAMPLE_RATE:
            os.environ["LANGSMITH_SAMPLE_RATE"] = str(self.LANGSMITH_SAMPLE_RATE)

    def get_s3_config(self) -> "S3Config":
        """Get S3 storage configuration."""
        from src.infra.storage.s3 import S3Config, S3Provider

        # Map provider string to enum
        provider_map = {
            "aws": S3Provider.AWS,
            "aliyun": S3Provider.ALIYUN,
            "tencent": S3Provider.TENCENT,
            "minio": S3Provider.MINIO,
            "custom": S3Provider.CUSTOM,
        }
        provider = provider_map.get(self.S3_PROVIDER.lower(), S3Provider.AWS)

        return S3Config(
            provider=provider,
            endpoint_url=self.S3_ENDPOINT_URL,
            access_key=self.S3_ACCESS_KEY,
            secret_key=self.S3_SECRET_KEY,
            region=self.S3_REGION,
            bucket_name=self.S3_BUCKET_NAME,
            custom_domain=self.S3_CUSTOM_DOMAIN,
            path_style=self.S3_PATH_STYLE,
            max_file_size=self.S3_MAX_FILE_SIZE,
            presigned_url_expires=self.S3_PRESIGNED_URL_EXPIRES,
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()


# SettingsService integration
_settings_service: Optional["SettingsService"] = None

# Cache for all settings from database
_settings_cache: dict[str, Any] = {}


async def initialize_settings() -> None:
    """Initialize settings from database, importing from .env if needed

    After calling this function, the global `settings` object will have its
    attributes overridden by values from the database (database > env > default).
    """
    global _settings_service, _settings_cache

    from src.infra.settings.service import SettingsService

    _settings_service = SettingsService.get_instance()
    await _settings_service.initialize()
    logger.info("[Settings] SettingsService initialized")

    # Load all settings from database and update the global settings object
    all_settings = await _settings_service.get_all(
        admin_mode=True, mask_sensitive=False
    )
    logger.info(f"[Settings] Loaded {len(all_settings)} categories from database")

    # Flatten the settings dict and cache them
    loaded_count = 0
    skipped_count = 0
    for category, items in all_settings.items():
        logger.debug(f"[Settings] Category {category}: {len(items)} items")
        for item in items:
            if item and item.value is not None:
                _settings_cache[item.key] = item.value
                # Only update if the field exists in Settings class
                if hasattr(settings, item.key):
                    setattr(settings, item.key, item.value)
                    loaded_count += 1
                else:
                    skipped_count += 1

    logger.info(f"[Settings] Loaded {loaded_count} settings into cache")
    logger.info(f"[Settings] REDIS_URL = {settings.REDIS_URL}")


async def refresh_settings(key: Optional[str] = None) -> None:
    """Refresh settings from database.

    Args:
        key: Specific key to refresh, or None for all settings.

    This should be called after database settings are updated.
    """
    global _settings_cache

    if _settings_service is None:
        return

    if key:
        # Refresh single setting
        setting = await _settings_service._storage.get_raw(key)
        if setting and setting.value is not None:
            _settings_cache[key] = setting.value
            setattr(settings, key, setting.value)
    else:
        # Refresh all settings
        all_settings = await _settings_service.get_all(
            admin_mode=True, mask_sensitive=False
        )
        for items in all_settings.values():
            for item in items:
                if item and item.value is not None:
                    _settings_cache[item.key] = item.value
                    setattr(settings, item.key, item.value)
