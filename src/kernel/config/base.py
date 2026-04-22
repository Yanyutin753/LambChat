"""Settings class definition."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from typing import TYPE_CHECKING, Any, Optional

from pydantic import Field
from pydantic_settings import BaseSettings

from src.infra.logging import get_logger

from .constants import JWT_SECRET_KEY_MIN_LENGTH
from .utils import (
    COMMIT_HASH,
    GIT_TAG,
    PROJECT_ROOT,
    expand_jwt_secret_key,
    get_app_version,
)

if TYPE_CHECKING:
    from src.infra.storage.s3 import S3Config

logger = get_logger(__name__)


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
    SESSION_MAX_EVENTS_PER_TRACE: int = 10000  # 单个 trace 最多保留的事件数，防止内存爆炸

    # ============================================
    # All settings below get defaults from SETTING_DEFINITIONS
    # ============================================

    # Application Settings
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    APP_BASE_URL: str = ""  # e.g. https://lambchat.example.com — 用于生成文件 URL 的固定前缀
    LOG_LEVEL: str = "INFO"

    # LLM Settings
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_DELAY: float = 1.0
    LLM_MODEL_CACHE_SIZE: int = 50  # 模型实例缓存大小，防止内存泄漏

    # MCP Settings
    ENABLE_MCP: bool = True
    ENABLE_DEFERRED_TOOL_LOADING: bool = True
    DEFERRED_TOOL_THRESHOLD: int = 20
    DEFERRED_TOOL_SEARCH_LIMIT: int = 25
    MCP_ENCRYPTION_SALT: Optional[str] = None  # 默认随机生成，确保加密一致性

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

    # Event Merger Settings
    ENABLE_EVENT_MERGER: bool = True  # 是否启用事件合并
    EVENT_MERGE_INTERVAL: float = 300.0  # 合并间隔（秒，默认 1 分钟）

    # Long-term Storage Settings
    ENABLE_POSTGRES_STORAGE: bool = False
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "langgraph"
    POSTGRES_POOL_MIN_SIZE: int = 2
    POSTGRES_POOL_MAX_SIZE: int = 10

    # Checkpoint Backend Settings
    CHECKPOINT_BACKEND: str = "mongodb"
    CHECKPOINT_PG_HOST: str = ""  # empty = fallback to POSTGRES_*
    CHECKPOINT_PG_PORT: int = 5432
    CHECKPOINT_PG_USER: str = ""
    CHECKPOINT_PG_PASSWORD: str = ""
    CHECKPOINT_PG_DB: str = ""
    CHECKPOINT_PG_POOL_MIN_SIZE: int = 2
    CHECKPOINT_PG_POOL_MAX_SIZE: int = 10

    # Sandbox Settings
    ENABLE_SANDBOX: bool = True
    SANDBOX_PLATFORM: str = "daytona"
    DAYTONA_API_KEY: str = ""
    DAYTONA_SERVER_URL: str = ""
    DAYTONA_TIMEOUT: int = 180
    DAYTONA_IMAGE: str = ""
    DAYTONA_AUTO_STOP_INTERVAL: int = 5
    DAYTONA_AUTO_ARCHIVE_INTERVAL: int = 5
    DAYTONA_AUTO_DELETE_INTERVAL: int = 1440

    # E2B Settings
    E2B_API_KEY: str = ""
    E2B_TEMPLATE: str = "base"
    E2B_TIMEOUT: int = 3600
    E2B_AUTO_PAUSE: bool = True
    E2B_AUTO_RESUME: bool = True

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
    S3_INTERNAL_UPLOAD_MAX_SIZE: int = 50 * 1024 * 1024
    S3_PUBLIC_BUCKET: bool = False
    S3_PRESIGNED_URL_EXPIRES: int = 7 * 24 * 3600

    # File Upload Settings
    LOCAL_STORAGE_PATH: str = "./uploads"
    FILE_UPLOAD_MAX_SIZE_IMAGE: int = 10
    FILE_UPLOAD_MAX_SIZE_VIDEO: int = 100
    FILE_UPLOAD_MAX_SIZE_AUDIO: int = 50
    FILE_UPLOAD_MAX_SIZE_DOCUMENT: int = 50
    FILE_UPLOAD_MAX_FILES: int = 10

    # Frontend Settings
    FRONTEND_DEV_URL: str = ""
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
    ADMIN_CONTACT_EMAIL: str = ""
    ADMIN_CONTACT_URL: str = ""

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

    # Memory Settings (Master Switch)
    ENABLE_MEMORY: bool = False

    # Native Memory Settings (MongoDB-backed, zero external deps)
    NATIVE_MEMORY_EMBEDDING_API_BASE: str = ""
    NATIVE_MEMORY_EMBEDDING_API_KEY: str = ""
    NATIVE_MEMORY_EMBEDDING_MODEL: str = "text-embedding-3-small"
    NATIVE_MEMORY_STALENESS_DAYS: int = 30
    NATIVE_MEMORY_PRUNE_THRESHOLD: int = 90
    NATIVE_MEMORY_INDEX_ENABLED: bool = True
    NATIVE_MEMORY_INDEX_CACHE_TTL: int = 300
    NATIVE_MEMORY_MODEL: str = ""
    NATIVE_MEMORY_API_BASE: str = ""
    NATIVE_MEMORY_API_KEY: str = ""
    NATIVE_MEMORY_RERANK_MODEL: str = ""
    NATIVE_MEMORY_RERANK_API_BASE: str = ""
    NATIVE_MEMORY_RERANK_API_KEY: str = ""
    NATIVE_MEMORY_MAX_TOKENS: int = 2000
    NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS: int = 1200
    NATIVE_MEMORY_STORE_NAMESPACE: str = "memories"
    NATIVE_MEMORY_APPEND_MAX_DETAILS: int = 8
    NATIVE_MEMORY_RECALL_MIN_SCORE: float = 0.3

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

        # Generate random MCP_ENCRYPTION_SALT if not set
        if not self.MCP_ENCRYPTION_SALT:
            self.MCP_ENCRYPTION_SALT = secrets.token_urlsafe(16)
            logger.info("MCP_ENCRYPTION_SALT not set, generated random salt")
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
            "local": S3Provider.LOCAL,
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
            internal_max_upload_size=self.S3_INTERNAL_UPLOAD_MAX_SIZE,
            presigned_url_expires=self.S3_PRESIGNED_URL_EXPIRES,
            storage_path=self.LOCAL_STORAGE_PATH,
        )

    @property
    def postgres_url(self) -> str:
        """Construct PostgreSQL connection URL from components."""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @property
    def checkpoint_postgres_url(self) -> str:
        """Construct checkpoint PostgreSQL connection URL. Falls back to shared POSTGRES_* when CHECKPOINT_PG_HOST is empty."""
        host = self.CHECKPOINT_PG_HOST or self.POSTGRES_HOST
        port = self.CHECKPOINT_PG_PORT
        user = self.CHECKPOINT_PG_USER or self.POSTGRES_USER
        password = self.CHECKPOINT_PG_PASSWORD or self.POSTGRES_PASSWORD
        db = self.CHECKPOINT_PG_DB or self.POSTGRES_DB
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
