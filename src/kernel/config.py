"""Configuration management using pydantic-settings."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from pydantic_settings import BaseSettings

if TYPE_CHECKING:
    from src.infra.settings.service import SettingsService
    from src.infra.storage.s3 import S3Config

from src.kernel.schemas.setting import SettingCategory, SettingType

# Minimum JWT secret key length (32 bytes for HS256)
JWT_SECRET_KEY_MIN_LENGTH = 32


def _expand_jwt_secret_key(key: str) -> str:
    """Expand a short JWT secret key to the minimum required length.

    Uses deterministic SHA-256 hashing to expand short keys to 32 bytes.
    This ensures the same input always produces the same output.

    Args:
        key: The original secret key (can be any length)

    Returns:
        A 32-byte URL-safe base64-encoded key
    """
    import base64

    if len(key) >= JWT_SECRET_KEY_MIN_LENGTH:
        return key

    # Use SHA-256 to deterministically expand the key
    # Repeatedly hash until we get 32 bytes
    result = key.encode("utf-8")
    while len(result) < 32:
        result = hashlib.sha256(result).digest()

    # Encode to URL-safe base64 (produces ~43-44 characters)
    return base64.urlsafe_b64encode(result).decode("utf-8").rstrip("=")


logger = logging.getLogger(__name__)
# Project root directory (where pyproject.toml is)
PROJECT_ROOT = Path(__file__).parent.parent.parent


def _get_app_version() -> str:
    """Read version from pyproject.toml."""
    pyproject_path = PROJECT_ROOT / "pyproject.toml"
    try:
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data.get("project", {}).get("version", "1.0.0")
    except Exception as e:
        logger.warning(f"Failed to read version from pyproject.toml: {e}")
        return "1.0.0"


# ============================================
# Settings that require server restart to take effect
# ============================================
RESTART_REQUIRED_SETTINGS = {
    "HOST",
    "PORT",
    "MONGODB_URL",
    "MONGODB_DB",
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
    "SESSION_TITLE_API_KEY",
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
    "POSTGRES_PASSWORD",
    "OAUTH_GOOGLE_CLIENT_SECRET",
    "OAUTH_GITHUB_CLIENT_SECRET",
    "OAUTH_APPLE_CLIENT_SECRET",
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
    "LLM_MAX_RETRIES": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "description": "LLM API 最大重试次数（用于处理 429 等错误）",
        "default": 3,
    },
    # ============================================
    # Session Settings
    # ============================================
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
    "SESSION_TITLE_MODEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "LLM model identifier (e.g., anthropic/claude-3-5-sonnet)",
        "default": "claude-3-5-haiku-20241022",
    },
    "SESSION_TITLE_API_BASE": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "LLM API base URL for title generation (leave empty to use main LLM API)",
        "default": "",
    },
    "SESSION_TITLE_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "LLM API key for title generation (leave empty to use main LLM API key)",
        "default": "",
    },
    "SESSION_TITLE_PROMPT": {
        "type": SettingType.TEXT,
        "category": SettingCategory.SESSION,
        "description": "Prompt template for generating session titles. Use {lang} and {message} as placeholders.",
        "default": "请您用简短的3-5个字的标题加上一个表情符号作为用户对话的提示标题。请您选取适合用于总结的表情符号来增强理解，但请避免使用符号或特殊格式。请您根据提示回复一个提示标题文本。\n\n回复示例：\n\n📉 股市趋势\n\n🍪 完美巧克力曲奇食谱\n\n🎮 视频游戏开发洞察\n\n# 重要\n\n1. 请务必用{lang}回复我\n2. 回复字数控制在3-5个字\n\nPrompt: {message}",
    },
    # ============================================
    # Sandbox Settings
    # ============================================
    "ENABLE_SANDBOX": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SANDBOX,
        "description": "Enable sandbox environment for running code",
        "default": False,
        "frontend_visible": True,
    },
    "SANDBOX_PLATFORM": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Sandbox platform: runloop, daytona, or modal",
        "default": "runloop",
        "depends_on": "ENABLE_SANDBOX",
    },
    "RUNLOOP_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Runloop API Key",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "runloop"},
    },
    "RUNLOOP_BASE_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Runloop API Base URL",
        "default": "https://api.runloop.ai",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "runloop"},
    },
    "DAYTONA_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona API Key",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_SERVER_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona Server URL",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_TIMEOUT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona command timeout in seconds",
        "default": 180,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_IMAGE": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona sandbox image (snapshot) to use for creating sandboxes",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "SANDBOX_AUTO_STOP_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "Sandbox auto-stop interval in minutes (stopped sandbox will be archived after this time)",
        "default": 5,
        "depends_on": "ENABLE_SANDBOX",
    },
    "SANDBOX_AUTO_ARCHIVE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "Sandbox auto-archive interval in minutes (archived sandbox will be deleted after this time)",
        "default": 5,
        "depends_on": "ENABLE_SANDBOX",
    },
    "SANDBOX_AUTO_DELETE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "Sandbox auto-delete interval in minutes after being archived",
        "default": 1440,
        "depends_on": "ENABLE_SANDBOX",
    },
    "MODAL_APP_NAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Modal App Name",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "modal"},
    },
    # ============================================
    # Skills Settings
    # ============================================
    "ENABLE_SKILLS": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SKILLS,
        "description": "Enable skills feature",
        "default": True,
        "frontend_visible": True,
    },
    # ============================================
    # Mcp Settings
    # ============================================
    "ENABLE_MCP": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.TOOLS,
        "description": "Enable MCP feature",
        "default": True,
        "frontend_visible": True,
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
    # PostgreSQL Settings (for LangGraph Store)
    # ============================================
    "POSTGRES_HOST": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "PostgreSQL host",
        "default": "localhost",
    },
    "POSTGRES_PORT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.DATABASE,
        "description": "PostgreSQL port",
        "default": 5432,
    },
    "POSTGRES_USER": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "PostgreSQL username",
        "default": "postgres",
    },
    "POSTGRES_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "PostgreSQL password",
        "default": "postgres",
    },
    "POSTGRES_DB": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "PostgreSQL database name",
        "default": "langgraph",
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
        "depends_on": "LANGSMITH_TRACING",
    },
    "LANGSMITH_PROJECT": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "description": "LangSmith project name",
        "default": "lamb-agent",
        "depends_on": "LANGSMITH_TRACING",
    },
    "LANGSMITH_API_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "description": "LangSmith API URL",
        "default": "https://api.smith.langchain.com",
        "depends_on": "LANGSMITH_TRACING",
    },
    "LANGSMITH_SAMPLE_RATE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.TRACING,
        "description": "LangSmith sample rate (0.0-1.0)",
        "default": 1.0,
        "depends_on": "LANGSMITH_TRACING",
    },
    # ============================================
    # JWT Authentication Settings
    # ============================================
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
        "frontend_visible": True,
    },
    "S3_PROVIDER": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 provider: aws, aliyun, tencent, minio, custom",
        "default": "aws",
        "depends_on": "S3_ENABLED",
    },
    "S3_ENDPOINT_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 endpoint URL (required for MinIO and custom providers)",
        "default": "",
        "depends_on": "S3_ENABLED",
    },
    "S3_ACCESS_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 access key",
        "default": "",
        "depends_on": "S3_ENABLED",
    },
    "S3_SECRET_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 secret key",
        "default": "",
        "depends_on": "S3_ENABLED",
    },
    "S3_REGION": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 region",
        "default": "us-east-1",
        "depends_on": "S3_ENABLED",
    },
    "S3_BUCKET_NAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 bucket name",
        "default": "",
        "depends_on": "S3_ENABLED",
    },
    "S3_CUSTOM_DOMAIN": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "Custom CDN domain for S3 files",
        "default": "",
        "depends_on": "S3_ENABLED",
    },
    "S3_PATH_STYLE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.S3,
        "description": "Use path-style URLs (required for MinIO)",
        "default": False,
        "depends_on": "S3_ENABLED",
    },
    "S3_MAX_FILE_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "Maximum file size in bytes (default: 10MB)",
        "default": 10485760,
        "depends_on": "S3_ENABLED",
    },
    "S3_PUBLIC_BUCKET": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.S3,
        "description": "Whether the S3 bucket is publicly readable",
        "default": False,
        "depends_on": "S3_ENABLED",
    },
    "S3_PRESIGNED_URL_EXPIRES": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "Presigned URL expiration time in seconds (default: 7 days)",
        "default": 604800,
        "depends_on": "S3_ENABLED",
    },
    # ============================================
    # User Management Settings
    # ============================================
    "DEFAULT_USER_ROLE": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "Default role for newly registered users",
        "default": "user",
    },
    "ENABLE_REGISTRATION": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.USER,
        "description": "Enable user registration",
        "default": True,
        "frontend_visible": True,
    },
    # ============================================
    # OAuth Settings
    # ============================================
    "OAUTH_GOOGLE_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.USER,
        "description": "Enable Google OAuth login",
        "default": False,
        "frontend_visible": True,
    },
    "OAUTH_GOOGLE_CLIENT_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "Google OAuth client ID",
        "default": "",
        "depends_on": "OAUTH_GOOGLE_ENABLED",
    },
    "OAUTH_GOOGLE_CLIENT_SECRET": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "Google OAuth client secret",
        "default": "",
        "depends_on": "OAUTH_GOOGLE_ENABLED",
    },
    "OAUTH_GITHUB_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.USER,
        "description": "Enable GitHub OAuth login",
        "default": False,
        "frontend_visible": True,
    },
    "OAUTH_GITHUB_CLIENT_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "GitHub OAuth client ID",
        "default": "",
        "depends_on": "OAUTH_GITHUB_ENABLED",
    },
    "OAUTH_GITHUB_CLIENT_SECRET": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "GitHub OAuth client secret",
        "default": "",
        "depends_on": "OAUTH_GITHUB_ENABLED",
    },
    "OAUTH_APPLE_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.USER,
        "description": "Enable Apple OAuth login",
        "default": False,
        "frontend_visible": True,
    },
    "OAUTH_APPLE_CLIENT_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "Apple OAuth client ID (Service ID)",
        "default": "",
        "depends_on": "OAUTH_APPLE_ENABLED",
    },
    "OAUTH_APPLE_CLIENT_SECRET": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "Apple OAuth client secret (private key)",
        "default": "",
        "depends_on": "OAUTH_APPLE_ENABLED",
    },
    "OAUTH_APPLE_TEAM_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "Apple developer team ID",
        "default": "",
        "depends_on": "OAUTH_APPLE_ENABLED",
    },
    "OAUTH_APPLE_KEY_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "Apple private key ID",
        "default": "",
        "depends_on": "OAUTH_APPLE_ENABLED",
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
        commit_hash = hash_result.stdout.strip() if hash_result.returncode == 0 else None

        # If describe looks like a tag (starts with v), use it as tag
        git_tag = describe if describe and describe.startswith("v") else None

        return git_tag, commit_hash
    except Exception:
        return None, None


# Get git info at module load time
_GIT_TAG, _COMMIT_HASH = _get_git_info()

# Import BaseSettings here to avoid forward reference issues


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Default values are defined in SETTING_DEFINITIONS (single source of truth).
    This class uses pydantic-settings to load from .env and environment variables.
    Runtime values can be updated from database via initialize_settings().
    """

    # Application (not in SETTING_DEFINITIONS - internal use only)
    APP_NAME: str = "LambChat"
    APP_VERSION: str = _get_app_version()

    # Version Info (populated at startup)
    GIT_TAG: Optional[str] = None
    COMMIT_HASH: Optional[str] = None
    BUILD_TIME: Optional[str] = None
    GITHUB_URL: str = "https://github.com/lambchat/lambchat"

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
    LLM_MAX_RETRIES: int = 3
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_BASE_URL: Optional[str] = None

    # MCP Settings
    ENABLE_MCP: bool = True

    # Session Settings
    SESSION_MAX_RUNS_PER_SESSION: int = 100
    ENABLE_MESSAGE_HISTORY: bool = True
    SSE_CACHE_TTL: int = 3600
    SESSION_TITLE_MODEL: str = "claude-3-5-haiku-20241022"
    SESSION_TITLE_API_BASE: str = ""
    SESSION_TITLE_API_KEY: str = ""
    SESSION_TITLE_PROMPT: str = "请您用简短的3-5个字的标题加上一个表情符号作为用户对话的提示标题。请您选取适合用于总结的表情符号来增强理解，但请避免使用符号或特殊格式。请您根据提示回复一个提示标题文本。\n\n回复示例：\n\n📉 股市趋势\n\n🍪 完美巧克力曲奇食谱\n\n🎮 视频游戏开发洞察\n\n# 重要\n\n1. 请务必用{lang}回复我\n2. 回复字数控制在3-5个字\n\nPrompt: {message}"

    # Redis Settings
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_PASSWORD: Optional[str] = None

    # MongoDB Settings
    MONGODB_URL: str = "mongodb://localhost:27017"
    MONGODB_DB: str = "agent_state"
    MONGODB_USERNAME: str = ""
    MONGODB_PASSWORD: str = ""
    MONGODB_AUTH_SOURCE: str = "admin"

    MONGODB_SESSIONS_COLLECTION: str = "sessions"
    MONGODB_TRACES_COLLECTION: str = "traces"

    # PostgreSQL Settings (for LangGraph Store - persistent memory/files)
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "langgraph"
    POSTGRES_POOL_MIN_SIZE: int = 5
    POSTGRES_POOL_MAX_SIZE: int = 50

    # Sandbox Settings
    ENABLE_SANDBOX: bool = True
    SANDBOX_PLATFORM: str = "runloop"  # runloop, daytona, modal
    RUNLOOP_API_KEY: str = ""
    RUNLOOP_BASE_URL: str = "https://api.runloop.ai"
    DAYTONA_API_KEY: str = ""
    DAYTONA_SERVER_URL: str = ""
    DAYTONA_TIMEOUT: int = 180  # 3 minutes
    DAYTONA_IMAGE: str = ""  # Optional: sandbox image/snapshot
    SANDBOX_AUTO_STOP_INTERVAL: int = 5  # minutes
    SANDBOX_AUTO_ARCHIVE_INTERVAL: int = 5  # minutes
    SANDBOX_AUTO_DELETE_INTERVAL: int = 1440  # minutes
    MODAL_APP_NAME: str = ""

    # Skills Settings
    ENABLE_SKILLS: bool = True

    # LangSmith Tracing Settings
    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: Optional[str] = None
    LANGSMITH_PROJECT: str = "lamb-agent"
    LANGSMITH_API_URL: str = "https://api.smith.langchain.com"
    LANGSMITH_SAMPLE_RATE: float = 1.0

    # JWT Authentication Settings
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
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
    ENABLE_REGISTRATION: bool = True

    # OAuth Settings
    OAUTH_GOOGLE_ENABLED: bool = False
    OAUTH_GOOGLE_CLIENT_ID: str = ""
    OAUTH_GOOGLE_CLIENT_SECRET: str = ""
    OAUTH_GITHUB_ENABLED: bool = False
    OAUTH_GITHUB_CLIENT_ID: str = ""
    OAUTH_GITHUB_CLIENT_SECRET: str = ""
    OAUTH_APPLE_ENABLED: bool = False
    OAUTH_APPLE_CLIENT_ID: str = ""
    OAUTH_APPLE_CLIENT_SECRET: str = ""
    OAUTH_APPLE_TEAM_ID: str = ""
    OAUTH_APPLE_KEY_ID: str = ""

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        # Generate random JWT_SECRET_KEY if not set or using placeholder
        if not self.JWT_SECRET_KEY or self.JWT_SECRET_KEY == "your-secret-key-change-in-production":
            self.JWT_SECRET_KEY = secrets.token_urlsafe(32)
            logger.warning(
                "JWT_SECRET_KEY not set or using placeholder value. "
                f"Generated random secret key: {self.JWT_SECRET_KEY[:8]}..."
            )
        # Expand short JWT_SECRET_KEY to meet minimum length requirement
        elif len(self.JWT_SECRET_KEY) < JWT_SECRET_KEY_MIN_LENGTH:
            original_key = self.JWT_SECRET_KEY
            self.JWT_SECRET_KEY = _expand_jwt_secret_key(self.JWT_SECRET_KEY)
            logger.warning(
                f"JWT_SECRET_KEY too short ({len(original_key)} bytes). "
                f"Expanded to meet minimum {JWT_SECRET_KEY_MIN_LENGTH} bytes requirement. "
                f"Expanded key prefix: {self.JWT_SECRET_KEY[:8]}..."
            )

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

    @property
    def postgres_url(self) -> str:
        """Construct PostgreSQL connection URL from components."""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"


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
    all_settings = await _settings_service.get_all(admin_mode=True, mask_sensitive=False)
    logger.info(f"[Settings] Loaded {len(all_settings)} categories from database")

    # Flatten the settings dict and cache them
    loaded_count = 0
    skipped_count = 0
    for category, items in all_settings.items():
        logger.debug(f"[Settings] Category {category}: {len(items)} items")
        for item in items:
            # Only update if value is not None AND not an empty string
            # This prevents empty DB values from overriding .env values
            if item and item.value is not None and item.value != "":
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
        # Only update if value is not None AND not an empty string
        if setting and setting.value is not None and setting.value != "":
            _settings_cache[key] = setting.value
            setattr(settings, key, setting.value)
    else:
        # Refresh all settings
        all_settings = await _settings_service.get_all(admin_mode=True, mask_sensitive=False)
        for items in all_settings.values():
            for item in items:
                # Only update if value is not None AND not an empty string
                if item and item.value is not None and item.value != "":
                    _settings_cache[item.key] = item.value
                    setattr(settings, item.key, item.value)
