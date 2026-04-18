"""Setting metadata definitions - single source of truth."""

from __future__ import annotations

# Re-export for convenience
from src.kernel.schemas.setting import JsonSchema, JsonSchemaField, SettingCategory, SettingType

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
        "description": "settingDesc.DEFAULT_AGENT",
        "default": "default",
        "frontend_visible": True,
    },
    "WELCOME_SUGGESTIONS": {
        "type": SettingType.JSON,
        "category": SettingCategory.FRONTEND,
        "description": "settingDesc.WELCOME_SUGGESTIONS",
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
        "json_schema": JsonSchema(
            type="object",
            key_label="settingDesc.WELCOME_SUGGESTION_LANG",
            value_type="array",
            item_label="settingDesc.WELCOME_SUGGESTION_ITEM",
            key_options=["en", "zh", "ja", "ko", "ru"],
            fields=[
                JsonSchemaField(
                    name="icon",
                    type="text",
                    label="settingDesc.WELCOME_SUGGESTION_ICON",
                    placeholder="🐍",
                    required=True,
                ),
                JsonSchemaField(
                    name="text",
                    type="text",
                    label="settingDesc.WELCOME_SUGGESTION_TEXT",
                    placeholder="...",
                    required=True,
                ),
            ],
        ),
    },
    # ============================================
    # Resend Email Settings (JSON schema)
    # ============================================
    "RESEND_ACCOUNTS": {
        "type": SettingType.JSON,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.RESEND_ACCOUNTS",
        "default": [],
        "depends_on": "EMAIL_ENABLED",
        "frontend_visible": True,
        "json_schema": JsonSchema(
            type="array",
            item_label="settingDesc.RESEND_ACCOUNT_ITEM",
            fields=[
                JsonSchemaField(
                    name="api_key",
                    type="password",
                    label="settingDesc.RESEND_ACCOUNT_API_KEY",
                    placeholder="re_xxxxxxxx",
                    required=True,
                ),
                JsonSchemaField(
                    name="email_from",
                    type="text",
                    label="settingDesc.RESEND_ACCOUNT_EMAIL_FROM",
                    placeholder="noreply@example.com",
                    required=True,
                ),
                JsonSchemaField(
                    name="email_from_name",
                    type="text",
                    label="settingDesc.RESEND_ACCOUNT_EMAIL_FROM_NAME",
                    placeholder="LambChat",
                ),
            ],
        ),
    },
    "ADMIN_CONTACT_EMAIL": {
        "type": SettingType.STRING,
        "category": SettingCategory.FRONTEND,
        "description": "settingDesc.ADMIN_CONTACT_EMAIL",
        "default": "",
        "frontend_visible": True,
    },
    "ADMIN_CONTACT_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.FRONTEND,
        "description": "settingDesc.ADMIN_CONTACT_URL",
        "default": "",
        "frontend_visible": True,
    },
    # ============================================
    # Application Settings
    # ============================================
    "APP_BASE_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.AGENT,
        "description": "settingDesc.APP_BASE_URL",
        "default": "",
        "frontend_visible": True,
    },
    "DEBUG": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.AGENT,
        "description": "settingDesc.DEBUG",
        "default": False,
    },
    "LOG_LEVEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.AGENT,
        "description": "settingDesc.LOG_LEVEL",
        "default": "INFO",
    },
    # ============================================
    # LLM Settings
    # ============================================
    "LLM_MAX_RETRIES": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "description": "settingDesc.LLM_MAX_RETRIES",
        "default": 3,
    },
    "LLM_RETRY_DELAY": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "description": "settingDesc.LLM_RETRY_DELAY",
        "default": 1.0,
    },
    "LLM_MODEL_CACHE_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "description": "settingDesc.LLM_MODEL_CACHE_SIZE",
        "default": 50,
    },
    # ============================================
    # Session Settings
    # ============================================
    "SESSION_MAX_RUNS_PER_SESSION": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.SESSION_MAX_RUNS_PER_SESSION",
        "default": 100,
    },
    "ENABLE_MESSAGE_HISTORY": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.ENABLE_MESSAGE_HISTORY",
        "default": True,
    },
    "SSE_CACHE_TTL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.SSE_CACHE_TTL",
        "default": 3600,
    },
    "SESSION_TITLE_MODEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.SESSION_TITLE_MODEL",
        "default": "claude-3-5-haiku-20241022",
    },
    "SESSION_TITLE_API_BASE": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.SESSION_TITLE_API_BASE",
        "default": "",
    },
    "SESSION_TITLE_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.SESSION_TITLE_API_KEY",
        "default": "",
        "is_sensitive": True,
    },
    "SESSION_TITLE_PROMPT": {
        "type": SettingType.TEXT,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.SESSION_TITLE_PROMPT",
        "default": "请您用简短的3-5个字的标题加上一个表情符号作为用户对话的提示标题。请您选取适合用于总结的表情符号来增强理解，但请避免使用符号或特殊格式。请您根据提示回复一个提示标题文本。\n\n回复示例：\n\n📉 股市趋势\n\n🍪 完美巧克力曲奇食谱\n\n🎮 视频游戏开发洞察\n\n# 重要\n\n1. 请务必用{lang}回复我\n2. 回复字数控制在3-5个字\n\nPrompt: {message}",
    },
    # ============================================
    # Event Merger Settings
    # ============================================
    "ENABLE_EVENT_MERGER": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.ENABLE_EVENT_MERGER",
        "default": True,
        "frontend_visible": True,
    },
    "EVENT_MERGE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.EVENT_MERGE_INTERVAL",
        "default": 300.0,
        "depends_on": "ENABLE_EVENT_MERGER",
    },
    # ============================================
    # Sandbox Settings
    # ============================================
    "ENABLE_SANDBOX": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.ENABLE_SANDBOX",
        "default": False,
        "frontend_visible": True,
    },
    "SANDBOX_PLATFORM": {
        "type": SettingType.SELECT,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.SANDBOX_PLATFORM",
        "default": "daytona",
        "depends_on": "ENABLE_SANDBOX",
        "options": ["daytona", "e2b"],
    },
    "DAYTONA_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.DAYTONA_API_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_SERVER_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.DAYTONA_SERVER_URL",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_TIMEOUT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.DAYTONA_TIMEOUT",
        "default": 180,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_IMAGE": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.DAYTONA_IMAGE",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_AUTO_STOP_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.DAYTONA_AUTO_STOP_INTERVAL",
        "default": 5,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_AUTO_ARCHIVE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.DAYTONA_AUTO_ARCHIVE_INTERVAL",
        "default": 5,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_AUTO_DELETE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.DAYTONA_AUTO_DELETE_INTERVAL",
        "default": 1440,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "E2B_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.E2B_API_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_TEMPLATE": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.E2B_TEMPLATE",
        "default": "base",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_TIMEOUT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.E2B_TIMEOUT",
        "default": 3600,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_AUTO_PAUSE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.E2B_AUTO_PAUSE",
        "default": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_AUTO_RESUME": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SANDBOX,
        "description": "settingDesc.E2B_AUTO_RESUME",
        "default": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    # ============================================
    # Skills Settings
    # ============================================
    "ENABLE_SKILLS": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SKILLS,
        "description": "settingDesc.ENABLE_SKILLS",
        "default": True,
        "frontend_visible": True,
    },
    # ============================================
    # Mcp Settings
    # ============================================
    "ENABLE_MCP": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.TOOLS,
        "description": "settingDesc.ENABLE_MCP",
        "default": True,
        "frontend_visible": True,
    },
    "ENABLE_DEFERRED_TOOL_LOADING": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.TOOLS,
        "description": "settingDesc.ENABLE_DEFERRED_TOOL_LOADING",
        "default": True,
        "depends_on": "ENABLE_MCP",
        "frontend_visible": True,
    },
    "DEFERRED_TOOL_THRESHOLD": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.TOOLS,
        "description": "settingDesc.DEFERRED_TOOL_THRESHOLD",
        "default": 20,
        "depends_on": "ENABLE_DEFERRED_TOOL_LOADING",
    },
    "DEFERRED_TOOL_SEARCH_LIMIT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.TOOLS,
        "description": "settingDesc.DEFERRED_TOOL_SEARCH_LIMIT",
        "default": 25,
        "depends_on": "ENABLE_DEFERRED_TOOL_LOADING",
    },
    # ============================================
    # Database Settings (MongoDB)
    # ============================================
    "MONGODB_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.MONGODB_URL",
        "default": "mongodb://localhost:27017",
        "is_sensitive": True,
    },
    "MONGODB_DB": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "description": "settingDesc.MONGODB_DB",
        "default": "agent_state",
    },
    "MONGODB_USERNAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.MONGODB_USERNAME",
        "default": "",
    },
    "MONGODB_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.MONGODB_PASSWORD",
        "default": "",
        "is_sensitive": True,
    },
    "MONGODB_AUTH_SOURCE": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.MONGODB_AUTH_SOURCE",
        "default": "admin",
    },
    # ============================================
    # Redis Settings
    # ============================================
    "REDIS_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.REDIS_URL",
        "default": "redis://localhost:6379/0",
        "is_sensitive": True,
    },
    "REDIS_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.REDIS_PASSWORD",
        "default": "",
        "is_sensitive": True,
    },
    # ============================================
    # LangSmith Tracing Settings
    # ============================================
    "LANGSMITH_TRACING": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.TRACING,
        "description": "settingDesc.LANGSMITH_TRACING",
        "default": False,
    },
    "LANGSMITH_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "description": "settingDesc.LANGSMITH_API_KEY",
        "default": "",
        "depends_on": "LANGSMITH_TRACING",
        "is_sensitive": True,
    },
    "LANGSMITH_PROJECT": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "description": "settingDesc.LANGSMITH_PROJECT",
        "default": "lamb-agent",
        "depends_on": "LANGSMITH_TRACING",
    },
    "LANGSMITH_API_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "description": "settingDesc.LANGSMITH_API_URL",
        "default": "https://api.smith.langchain.com",
        "depends_on": "LANGSMITH_TRACING",
    },
    "LANGSMITH_SAMPLE_RATE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.TRACING,
        "description": "settingDesc.LANGSMITH_SAMPLE_RATE",
        "default": 1.0,
        "depends_on": "LANGSMITH_TRACING",
    },
    # ============================================
    # JWT Authentication Settings
    # ============================================
    "JWT_ALGORITHM": {
        "type": SettingType.STRING,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.JWT_ALGORITHM",
        "default": "HS256",
    },
    "ACCESS_TOKEN_EXPIRE_HOURS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.ACCESS_TOKEN_EXPIRE_HOURS",
        "default": 24,
    },
    "REFRESH_TOKEN_EXPIRE_DAYS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.REFRESH_TOKEN_EXPIRE_DAYS",
        "default": 7,
    },
    # ============================================
    # S3 Storage Settings
    # ============================================
    "S3_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_ENABLED",
        "default": False,
        "frontend_visible": True,
    },
    "S3_PROVIDER": {
        "type": SettingType.SELECT,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_PROVIDER",
        "default": "aws",
        "depends_on": "S3_ENABLED",
        "options": ["aws", "aliyun", "tencent", "minio", "custom"],
    },
    "S3_ENDPOINT_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_ENDPOINT_URL",
        "default": "",
        "depends_on": "S3_ENABLED",
    },
    "S3_ACCESS_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_ACCESS_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": "S3_ENABLED",
    },
    "S3_SECRET_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_SECRET_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": "S3_ENABLED",
    },
    "S3_REGION": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_REGION",
        "default": "us-east-1",
        "depends_on": "S3_ENABLED",
    },
    "S3_BUCKET_NAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_BUCKET_NAME",
        "default": "",
        "depends_on": "S3_ENABLED",
    },
    "S3_CUSTOM_DOMAIN": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_CUSTOM_DOMAIN",
        "default": "",
        "depends_on": "S3_ENABLED",
    },
    "S3_PATH_STYLE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_PATH_STYLE",
        "default": False,
        "depends_on": "S3_ENABLED",
    },
    "S3_MAX_FILE_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_MAX_FILE_SIZE",
        "default": 10485760,
        "depends_on": "S3_ENABLED",
    },
    "S3_INTERNAL_UPLOAD_MAX_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_INTERNAL_UPLOAD_MAX_SIZE",
        "default": 52428800,
        "depends_on": "S3_ENABLED",
    },
    "S3_PUBLIC_BUCKET": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_PUBLIC_BUCKET",
        "default": False,
        "depends_on": "S3_ENABLED",
    },
    "S3_PRESIGNED_URL_EXPIRES": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "settingDesc.S3_PRESIGNED_URL_EXPIRES",
        "default": 604800,
        "depends_on": "S3_ENABLED",
    },
    # ============================================
    # File Upload Limits
    # ============================================
    "LOCAL_STORAGE_PATH": {
        "type": SettingType.STRING,
        "category": SettingCategory.S3,
        "description": "settingDesc.LOCAL_STORAGE_PATH",
        "default": "./uploads",
    },
    "FILE_UPLOAD_MAX_SIZE_IMAGE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "settingDesc.FILE_UPLOAD_MAX_SIZE_IMAGE",
        "default": 10,
    },
    "FILE_UPLOAD_MAX_SIZE_VIDEO": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "settingDesc.FILE_UPLOAD_MAX_SIZE_VIDEO",
        "default": 100,
    },
    "FILE_UPLOAD_MAX_SIZE_AUDIO": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "settingDesc.FILE_UPLOAD_MAX_SIZE_AUDIO",
        "default": 50,
    },
    "FILE_UPLOAD_MAX_SIZE_DOCUMENT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "settingDesc.FILE_UPLOAD_MAX_SIZE_DOCUMENT",
        "default": 50,
    },
    "FILE_UPLOAD_MAX_FILES": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.S3,
        "description": "settingDesc.FILE_UPLOAD_MAX_FILES",
        "default": 10,
    },
    # ============================================
    # Long-term Storage Settings (PostgreSQL)
    # ============================================
    "ENABLE_POSTGRES_STORAGE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "settingDesc.ENABLE_POSTGRES_STORAGE",
        "default": False,
        "frontend_visible": True,
    },
    "POSTGRES_HOST": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "settingDesc.POSTGRES_HOST",
        "default": "localhost",
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_PORT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "settingDesc.POSTGRES_PORT",
        "default": 5432,
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_USER": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "settingDesc.POSTGRES_USER",
        "default": "postgres",
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "settingDesc.POSTGRES_PASSWORD",
        "default": "postgres",
        "is_sensitive": True,
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_DB": {
        "type": SettingType.STRING,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "settingDesc.POSTGRES_DB",
        "default": "langgraph",
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_POOL_MIN_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "settingDesc.POSTGRES_POOL_MIN_SIZE",
        "default": 2,
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    "POSTGRES_POOL_MAX_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LONG_TERM_STORAGE,
        "description": "settingDesc.POSTGRES_POOL_MAX_SIZE",
        "default": 10,
        "depends_on": "ENABLE_POSTGRES_STORAGE",
    },
    # ============================================
    # Checkpoint Backend Settings
    # ============================================
    "CHECKPOINT_BACKEND": {
        "type": SettingType.SELECT,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.CHECKPOINT_BACKEND",
        "default": "mongodb",
        "options": ["mongodb", "postgres"],
        "frontend_visible": True,
    },
    "CHECKPOINT_PG_HOST": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.CHECKPOINT_PG_HOST",
        "default": "",
        "depends_on": {"key": "CHECKPOINT_BACKEND", "value": "postgres"},
    },
    "CHECKPOINT_PG_PORT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.CHECKPOINT_PG_PORT",
        "default": 5432,
        "depends_on": {"key": "CHECKPOINT_BACKEND", "value": "postgres"},
    },
    "CHECKPOINT_PG_USER": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.CHECKPOINT_PG_USER",
        "default": "",
        "depends_on": {"key": "CHECKPOINT_BACKEND", "value": "postgres"},
    },
    "CHECKPOINT_PG_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.CHECKPOINT_PG_PASSWORD",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "CHECKPOINT_BACKEND", "value": "postgres"},
    },
    "CHECKPOINT_PG_DB": {
        "type": SettingType.STRING,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.CHECKPOINT_PG_DB",
        "default": "",
        "depends_on": {"key": "CHECKPOINT_BACKEND", "value": "postgres"},
    },
    "CHECKPOINT_PG_POOL_MIN_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.CHECKPOINT_PG_POOL_MIN_SIZE",
        "default": 2,
        "depends_on": {"key": "CHECKPOINT_BACKEND", "value": "postgres"},
    },
    "CHECKPOINT_PG_POOL_MAX_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.DATABASE,
        "description": "settingDesc.CHECKPOINT_PG_POOL_MAX_SIZE",
        "default": 10,
        "depends_on": {"key": "CHECKPOINT_BACKEND", "value": "postgres"},
    },
    # ============================================
    # User Management Settings
    # ============================================
    "DEFAULT_USER_ROLE": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "settingDesc.DEFAULT_USER_ROLE",
        "default": "user",
    },
    "ENABLE_REGISTRATION": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.USER,
        "description": "settingDesc.ENABLE_REGISTRATION",
        "default": True,
        "frontend_visible": True,
    },
    # ============================================
    # OAuth Settings
    # ============================================
    "OAUTH_GOOGLE_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_GOOGLE_ENABLED",
        "default": False,
        "frontend_visible": True,
    },
    "OAUTH_GOOGLE_CLIENT_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_GOOGLE_CLIENT_ID",
        "default": "",
        "depends_on": "OAUTH_GOOGLE_ENABLED",
    },
    "OAUTH_GOOGLE_CLIENT_SECRET": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_GOOGLE_CLIENT_SECRET",
        "default": "",
        "depends_on": "OAUTH_GOOGLE_ENABLED",
        "is_sensitive": True,
    },
    "OAUTH_GITHUB_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_GITHUB_ENABLED",
        "default": False,
        "frontend_visible": True,
    },
    "OAUTH_GITHUB_CLIENT_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_GITHUB_CLIENT_ID",
        "default": "",
        "depends_on": "OAUTH_GITHUB_ENABLED",
    },
    "OAUTH_GITHUB_CLIENT_SECRET": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_GITHUB_CLIENT_SECRET",
        "default": "",
        "depends_on": "OAUTH_GITHUB_ENABLED",
        "is_sensitive": True,
    },
    "OAUTH_APPLE_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_APPLE_ENABLED",
        "default": False,
        "frontend_visible": True,
    },
    "OAUTH_APPLE_CLIENT_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_APPLE_CLIENT_ID",
        "default": "",
        "depends_on": "OAUTH_APPLE_ENABLED",
    },
    "OAUTH_APPLE_CLIENT_SECRET": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_APPLE_CLIENT_SECRET",
        "default": "",
        "depends_on": "OAUTH_APPLE_ENABLED",
        "is_sensitive": True,
    },
    "OAUTH_APPLE_TEAM_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_APPLE_TEAM_ID",
        "default": "",
        "depends_on": "OAUTH_APPLE_ENABLED",
    },
    "OAUTH_APPLE_KEY_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.USER,
        "description": "settingDesc.OAUTH_APPLE_KEY_ID",
        "default": "",
        "depends_on": "OAUTH_APPLE_ENABLED",
    },
    # ============================================
    # Cloudflare Turnstile Settings
    # ============================================
    "TURNSTILE_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.TURNSTILE_ENABLED",
        "default": False,
        "frontend_visible": True,
    },
    "TURNSTILE_SITE_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.TURNSTILE_SITE_KEY",
        "default": "",
        "depends_on": "TURNSTILE_ENABLED",
        "frontend_visible": True,
    },
    "TURNSTILE_SECRET_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.TURNSTILE_SECRET_KEY",
        "default": "",
        "depends_on": "TURNSTILE_ENABLED",
        "is_sensitive": True,
    },
    "TURNSTILE_REQUIRE_ON_LOGIN": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.TURNSTILE_REQUIRE_ON_LOGIN",
        "default": False,
        "depends_on": "TURNSTILE_ENABLED",
        "frontend_visible": True,
    },
    "TURNSTILE_REQUIRE_ON_REGISTER": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.TURNSTILE_REQUIRE_ON_REGISTER",
        "default": True,
        "depends_on": "TURNSTILE_ENABLED",
        "frontend_visible": True,
    },
    "TURNSTILE_REQUIRE_ON_PASSWORD_CHANGE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.TURNSTILE_REQUIRE_ON_PASSWORD_CHANGE",
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
        "description": "settingDesc.EMAIL_ENABLED",
        "default": False,
        "frontend_visible": True,
    },
    "PASSWORD_RESET_EXPIRE_HOURS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.PASSWORD_RESET_EXPIRE_HOURS",
        "default": 24,
        "depends_on": "EMAIL_ENABLED",
    },
    "REQUIRE_EMAIL_VERIFICATION": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SECURITY,
        "description": "settingDesc.REQUIRE_EMAIL_VERIFICATION",
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
        "description": "settingDesc.ENABLE_MEMORY",
        "default": False,
        "frontend_visible": True,
    },
    "MEMORY_PERFORM": {
        "type": SettingType.SELECT,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.MEMORY_PERFORM",
        "default": "memu",
        "depends_on": "ENABLE_MEMORY",
        "options": ["memu", "hindsight", "native"],
    },
    # ============================================
    # Hindsight Memory Settings
    # ============================================
    "HINDSIGHT_BASE_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.HINDSIGHT_BASE_URL",
        "default": "",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "hindsight"},
    },
    "HINDSIGHT_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.HINDSIGHT_API_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "hindsight"},
    },
    "HINDSIGHT_MAX_CONCURRENT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.HINDSIGHT_MAX_CONCURRENT",
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
        "description": "settingDesc.MEMU_API_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "memu"},
    },
    "MEMU_BASE_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.MEMU_BASE_URL",
        "default": "https://api.memu.so",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "memu"},
    },
    # ============================================
    # Native Memory Settings (MongoDB-backed, zero external deps)
    # ============================================
    "NATIVE_MEMORY_EMBEDDING_API_BASE": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_EMBEDDING_API_BASE",
        "default": "",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_EMBEDDING_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_EMBEDDING_API_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_EMBEDDING_MODEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_EMBEDDING_MODEL",
        "default": "text-embedding-3-small",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_STALENESS_DAYS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_STALENESS_DAYS",
        "default": 30,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_PRUNE_THRESHOLD": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_PRUNE_THRESHOLD",
        "default": 90,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_INDEX_ENABLED": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_INDEX_ENABLED",
        "default": True,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
        "frontend_visible": True,
    },
    "NATIVE_MEMORY_INDEX_CACHE_TTL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_INDEX_CACHE_TTL",
        "default": 300,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_MODEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_MODEL",
        "default": "",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_API_BASE": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_API_BASE",
        "default": "",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_API_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_RERANK_MODEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_RERANK_MODEL",
        "default": "",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_RERANK_API_BASE": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_RERANK_API_BASE",
        "default": "",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_RERANK_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_RERANK_API_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_MAX_TOKENS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_MAX_TOKENS",
        "default": 2000,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_INLINE_CONTENT_MAX_CHARS",
        "default": 1200,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_STORE_NAMESPACE": {
        "type": SettingType.STRING,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_STORE_NAMESPACE",
        "default": "memories",
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
    "NATIVE_MEMORY_APPEND_MAX_DETAILS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.MEMORY,
        "description": "settingDesc.NATIVE_MEMORY_APPEND_MAX_DETAILS",
        "default": 8,
        "depends_on": {"key": "MEMORY_PERFORM", "value": "native"},
    },
}
