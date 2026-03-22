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
        "description": "Welcome page suggestions displayed to users (multi-language JSON object keyed by language code)",
        "default": {
            "en": [
                {"icon": "🐍", "text": "Create a Python hello world script"},
                {"icon": "📁", "text": "List files in the workspace directory"},
                {"icon": "📄", "text": "Read the README.md file"},
                {"icon": "🔧", "text": "Help me write a shell script"},
            ],
            "zh": [
                {"icon": "🐍", "text": "创建一个 Python Hello World 脚本"},
                {"icon": "📁", "text": "列出工作区目录中的文件"},
                {"icon": "📄", "text": "读取 README.md 文件"},
                {"icon": "🔧", "text": "帮我写一个 Shell 脚本"},
            ],
            "ja": [
                {"icon": "🐍", "text": "PythonのHello Worldスクリプトを作成"},
                {"icon": "📁", "text": "ワークスペースディレクトリのファイルを一覧表示"},
                {"icon": "📄", "text": "README.mdファイルを読む"},
                {"icon": "🔧", "text": "シェルスクリプトを書くのを手伝って"},
            ],
            "ko": [
                {"icon": "🐍", "text": "Python Hello World 스크립트 만들기"},
                {"icon": "📁", "text": "작업 공간 디렉토리의 파일 목록 보기"},
                {"icon": "📄", "text": "README.md 파일 읽기"},
                {"icon": "🔧", "text": "쉘 스크립트 작성 도와줘"},
            ],
            "ru": [
                {"icon": "🐍", "text": "Создайте скрипт Python Hello World"},
                {"icon": "📁", "text": "Покажите файлы в рабочей директории"},
                {"icon": "📄", "text": "Прочитайте файл README.md"},
                {"icon": "🔧", "text": "Помогите написать скрипт оболочки"},
            ],
        },
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
        "is_sensitive": True,
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
    "LLM_RETRY_DELAY": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "description": "LLM API 重试基础等待时间（秒，指数退避起始值）",
        "default": 1.0,
    },
    "LLM_MAX_INPUT_TOKENS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "description": "LLM 上下文窗口大小，用于 DeepAgent 自动压缩对话（设为 None 则使用模型默认值）",
        "default": None,
        "nullable": True,
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
        "is_sensitive": True,
    },
    "SESSION_TITLE_PROMPT": {
        "type": SettingType.TEXT,
        "category": SettingCategory.SESSION,
        "description": "Prompt template for generating session titles. Use {lang} and {message} as placeholders.",
        "default": "请您用简短的3-5个字的标题加上一个表情符号作为用户对话的提示标题。请您选取适合用于总结的表情符号来增强理解，但请避免使用符号或特殊格式。请您根据提示回复一个提示标题文本。\n\n回复示例：\n\n📉 股市趋势\n\n🍪 完美巧克力曲奇食谱\n\n🎮 视频游戏开发洞察\n\n# 重要\n\n1. 请务必用{lang}回复我\n2. 回复字数控制在3-5个字\n\nPrompt: {message}",
    },
    # ============================================
    # Event Merger Settings
    # ============================================
    "ENABLE_EVENT_MERGER": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SESSION,
        "description": "Enable event merger to reduce event count",
        "default": True,
        "frontend_visible": True,
    },
    "EVENT_MERGE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "description": "Event merge interval in seconds",
        "default": 300.0,
        "depends_on": "ENABLE_EVENT_MERGER",
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
        "type": SettingType.SELECT,
        "category": SettingCategory.SANDBOX,
        "description": "Sandbox platform to use",
        "default": "runloop",
        "depends_on": "ENABLE_SANDBOX",
        "options": ["runloop", "daytona", "modal", "e2b"],
    },
    "RUNLOOP_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Runloop API Key",
        "default": "",
        "is_sensitive": True,
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
        "is_sensitive": True,
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
    "DAYTONA_AUTO_STOP_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona sandbox auto-stop interval in minutes",
        "default": 5,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_AUTO_ARCHIVE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona sandbox auto-archive interval in minutes",
        "default": 5,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_AUTO_DELETE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "Daytona sandbox auto-delete interval in minutes after being archived",
        "default": 1440,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "MODAL_APP_NAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "Modal App Name",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "modal"},
    },
    "E2B_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "E2B API Key",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_TEMPLATE": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "E2B sandbox template name (e.g. 'base')",
        "default": "base",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_TIMEOUT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "E2B sandbox timeout in seconds (max 3600 on Hobby, 86400 on Pro)",
        "default": 3600,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_AUTO_PAUSE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SANDBOX,
        "description": "Automatically pause sandbox on timeout instead of killing (preserves filesystem and memory state)",
        "default": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_AUTO_RESUME": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SANDBOX,
        "description": "Automatically resume paused sandbox on next activity (requires E2B_AUTO_PAUSE)",
        "default": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
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
        "is_sensitive": True,
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
        "is_sensitive": True,
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
        "is_sensitive": True,
    },
    "REDIS_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "Redis password",
        "default": "",
        "is_sensitive": True,
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
        "is_sensitive": True,
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
        "type": SettingType.SELECT,
        "category": SettingCategory.S3,
        "description": "S3 provider to use",
        "default": "aws",
        "depends_on": "S3_ENABLED",
        "options": ["aws", "aliyun", "tencent", "minio", "custom"],
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
        "is_sensitive": True,
        "depends_on": "S3_ENABLED",
    },
    "S3_SECRET_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "S3 secret key",
        "default": "",
        "is_sensitive": True,
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
    # File Upload Limits
    # ============================================
    "LOCAL_STORAGE_PATH": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "Local storage path when S3 is not enabled (default: ./uploads)",
        "default": "./uploads",
    },
    "FILE_UPLOAD_MAX_SIZE_IMAGE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "Maximum image file size in MB",
        "default": 10,
    },
    "FILE_UPLOAD_MAX_SIZE_VIDEO": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "Maximum video file size in MB",
        "default": 100,
    },
    "FILE_UPLOAD_MAX_SIZE_AUDIO": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "Maximum audio file size in MB",
        "default": 50,
    },
    "FILE_UPLOAD_MAX_SIZE_DOCUMENT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "Maximum document file size in MB",
        "default": 50,
    },
    "FILE_UPLOAD_MAX_FILES": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "Maximum number of files per upload",
        "default": 10,
    },
    # ============================================
    # Long-term Storage Settings (PostgreSQL)
    # ============================================
    "ENABLE_POSTGRES_STORAGE": {
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
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_PORT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL port",
        "default": 5432,
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_USER": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL username",
        "default": "postgres",
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL password",
        "default": "postgres",
        "is_sensitive": True,
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_DB": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL database name",
        "default": "langgraph",
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_POOL_MIN_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL connection pool minimum size",
        "default": 2,
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_POOL_MAX_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "PostgreSQL connection pool maximum size",
        "default": 10,
        "depends_on": "ENABLE_POSTGRES_STORAGE",
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
        "is_sensitive": True,
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
        "is_sensitive": True,
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
        "is_sensitive": True,
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
        "is_sensitive": True,
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
    # ============================================
    # Memory Settings (Master Switch)
    # ============================================
    "ENABLE_MEMORY": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.MEMORY,
        "description": "Enable cross-session memory feature (master switch)",
        "default": False,
        "frontend_visible": True,
    },
    "MEMORY_PERFORM": {
        "type": SettingType.SELECT,
        "category": SettingCategory.MEMORY,
        "description": "Memory provider to use",
        "default": "memu",
        "depends_on": "ENABLE_MEMORY",
        "options": ["memu", "hindsight"],
    },
    # ============================================
    # Hindsight Memory Settings
    # ============================================
    "HINDSIGHT_BASE_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "Hindsight server URL (required, e.g., http://localhost:8888)",
        "default": "",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "hindsight"},
    },
    "HINDSIGHT_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "Hindsight API key (optional, depends on server config)",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "hindsight"},
    },
    "HINDSIGHT_MAX_CONCURRENT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.MEMORY,
        "description": "Maximum concurrent API calls to Hindsight service (per worker process)",
        "default": 64,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "hindsight"},
        "frontend_visible": True,
    },
    # ============================================
    # memU Memory Settings
    # ============================================
    "MEMU_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "memU API key (get from https://app.memu.so/quick-start)",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "memu"},
    },
    "MEMU_BASE_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "memU cloud API base URL",
        "default": "https://api.memu.so",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "memu"},
    },
}
