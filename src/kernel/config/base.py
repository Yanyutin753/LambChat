"""Settings class definition."""

from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

from .constants import JWT_SECRET_KEY_MIN_LENGTH
from .utils import COMMIT_HASH, GIT_TAG, PROJECT_ROOT, expand_jwt_secret_key, get_app_version

if TYPE_CHECKING:
    from src.infra.storage.s3 import S3Config

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Default values are defined in SETTING_DEFINITIONS (single source of truth).
    This class uses pydantic-settings to load from .env and environment variables.
    Runtime values can be updated from database via initialize_settings().
    """

    # Application (not in SETTING_DEFINITIONS - internal use only)
    APP_NAME: str = "LambChat"
    APP_VERSION: str = Field(default_factory=get_app_version)

    # Version Info (populated at startup)
    GIT_TAG: Optional[str] = None
    COMMIT_HASH: Optional[str] = None
    BUILD_TIME: Optional[str] = None
    GITHUB_URL: str = "https://github.com/Yanyutin753/LambChat"

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

    # Long-term Storage Settings (PostgreSQL for LangGraph Store)
    ENABLE_LONG_TERM_STORAGE: bool = False
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "langgraph"
    POSTGRES_POOL_MIN_SIZE: int = 2
    POSTGRES_POOL_MAX_SIZE: int = 10

    # Sandbox Settings
    ENABLE_SANDBOX: bool = True
    SANDBOX_PLATFORM: str = "runloop"
    RUNLOOP_API_KEY: str = ""
    RUNLOOP_BASE_URL: str = "https://api.runloop.ai"
    DAYTONA_API_KEY: str = ""
    DAYTONA_SERVER_URL: str = ""
    DAYTONA_TIMEOUT: int = 180
    DAYTONA_IMAGE: str = ""
    SANDBOX_AUTO_STOP_INTERVAL: int = 5
    SANDBOX_AUTO_ARCHIVE_INTERVAL: int = 5
    SANDBOX_AUTO_DELETE_INTERVAL: int = 1440
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
    JWT_SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
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
    S3_PRESIGNED_URL_EXPIRES: int = 7 * 24 * 3600

    # Frontend Settings
    DEFAULT_AGENT: str = "default"
    WELCOME_SUGGESTIONS: list = Field(
        default_factory=lambda: [
            {"icon": "🐍", "text": "Create a Python hello world script"},
            {"icon": "📁", "text": "List files in the workspace directory"},
            {"icon": "📄", "text": "Read the README.md file"},
            {"icon": "🔧", "text": "Help me write a shell script"},
        ]
    )
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

    # Cloudflare Turnstile Settings
    TURNSTILE_ENABLED: bool = False
    TURNSTILE_SITE_KEY: str = ""
    TURNSTILE_SECRET_KEY: str = ""
    TURNSTILE_REQUIRE_ON_LOGIN: bool = False
    TURNSTILE_REQUIRE_ON_REGISTER: bool = True
    TURNSTILE_REQUIRE_ON_PASSWORD_CHANGE: bool = True

    # Email Settings (Resend)
    EMAIL_ENABLED: bool = False
    RESEND_ACCOUNTS: Any = Field(default_factory=list)
    PASSWORD_RESET_EXPIRE_HOURS: int = 24
    REQUIRE_EMAIL_VERIFICATION: bool = False

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
            self.JWT_SECRET_KEY = expand_jwt_secret_key(self.JWT_SECRET_KEY)
            logger.warning(
                f"JWT_SECRET_KEY too short ({len(original_key)} bytes). "
                f"Expanded to meet minimum {JWT_SECRET_KEY_MIN_LENGTH} bytes requirement. "
                f"Expanded key prefix: {self.JWT_SECRET_KEY[:8]}..."
            )

        # Set version info from git (if not already set via env)
        if self.GIT_TAG is None:
            self.GIT_TAG = GIT_TAG
        if self.COMMIT_HASH is None:
            self.COMMIT_HASH = COMMIT_HASH
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
