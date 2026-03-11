"""Setting metadata definitions - single source of truth."""

from __future__ import annotations

from src.kernel.schemas.setting import SettingCategory, SettingType

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
        "description": "Sandbox auto-stop interval in minutes",
        "default": 5,
        "depends_on": "ENABLE_SANDBOX",
    },
    "SANDBOX_AUTO_ARCHIVE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "Sandbox auto-archive interval in minutes",
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
    # Long-term Storage Settings (PostgreSQL)
    # ============================================
    "ENABLE_LONG_TERM_STORAGE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "Enable PostgreSQL-based long-term storage",
        "default": False,
        "frontend_visible": True,
    },
    "POSTGRES_HOST": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL host",
        "default": "localhost",
        "depends_on": "ENABLE_LONG_TERM_STORAGE",
    },
    "POSTGRES_PORT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL port",
        "default": 5432,
        "depends_on": "ENABLE_LONG_TERM_STORAGE",
    },
    "POSTGRES_USER": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL username",
        "default": "postgres",
        "depends_on": "ENABLE_LONG_TERM_STORAGE",
    },
    "POSTGRES_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL password",
        "default": "postgres",
        "is_sensitive": True,
        "depends_on": "ENABLE_LONG_TERM_STORAGE",
    },
    "POSTGRES_DB": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL database name",
        "default": "langgraph",
        "depends_on": "ENABLE_LONG_TERM_STORAGE",
    },
    "POSTGRES_POOL_MIN_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL connection pool minimum size",
        "default": 2,
        "depends_on": "ENABLE_LONG_TERM_STORAGE",
    },
    "POSTGRES_POOL_MAX_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL connection pool maximum size",
        "default": 10,
        "depends_on": "ENABLE_LONG_TERM_STORAGE",
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
    # ============================================
    # Cloudflare Turnstile Settings
    # ============================================
    "TURNSTILE_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "Enable Cloudflare Turnstile verification",
        "default": False,
        "frontend_visible": True,
    },
    "TURNSTILE_SITE_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SECURITY,
        "description": "Cloudflare Turnstile site key",
        "default": "",
        "depends_on": "TURNSTILE_ENABLED",
        "frontend_visible": True,
    },
    "TURNSTILE_SECRET_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SECURITY,
        "description": "Cloudflare Turnstile secret key",
        "default": "",
        "depends_on": "TURNSTILE_ENABLED",
    },
    "TURNSTILE_REQUIRE_ON_LOGIN": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "Require Turnstile verification on login",
        "default": False,
        "depends_on": "TURNSTILE_ENABLED",
        "frontend_visible": True,
    },
    "TURNSTILE_REQUIRE_ON_REGISTER": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "Require Turnstile verification on registration",
        "default": True,
        "depends_on": "TURNSTILE_ENABLED",
        "frontend_visible": True,
    },
    "TURNSTILE_REQUIRE_ON_PASSWORD_CHANGE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "Require Turnstile verification on password change",
        "default": True,
        "depends_on": "TURNSTILE_ENABLED",
        "frontend_visible": True,
    },
    # ============================================
    # Email Settings (Resend)
    # ============================================
    "EMAIL_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "Enable email service (password reset, email verification)",
        "default": False,
        "frontend_visible": True,
    },
    "RESEND_ACCOUNTS": {
        "type": SettingType.JSON,
        "category": SettingCategory.SECURITY,
        "description": "Resend accounts config (supports multiple accounts)",
        "default": [],
        "depends_on": "EMAIL_ENABLED",
        "frontend_visible": True,
    },
    "PASSWORD_RESET_EXPIRE_HOURS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SECURITY,
        "description": "Password reset link expiration in hours",
        "default": 24,
        "depends_on": "EMAIL_ENABLED",
    },
    "REQUIRE_EMAIL_VERIFICATION": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "Require email verification before login",
        "default": False,
        "depends_on": "EMAIL_ENABLED",
        "frontend_visible": True,
    },
}
