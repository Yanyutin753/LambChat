"""Setting metadata definitions - single source of truth."""

from __future__ import annotations

from src.kernel.config._definitions_extra import EXTRA_SETTING_DEFINITIONS

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
        "subcategory": "display",
        "description": "settingDesc.DEFAULT_AGENT",
        "default": "default",
        "frontend_visible": True,
    },
    "WELCOME_SUGGESTIONS": {
        "type": SettingType.JSON,
        "category": SettingCategory.FRONTEND,
        "subcategory": "display",
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
    # Email Service Settings (Resend)
    # ============================================
    "RESEND_ACCOUNTS": {
        "type": SettingType.JSON,
        "category": SettingCategory.EMAIL,
        "subcategory": "service",
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
        "subcategory": "contact",
        "description": "settingDesc.ADMIN_CONTACT_EMAIL",
        "default": "",
        "frontend_visible": True,
    },
    "ADMIN_CONTACT_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.FRONTEND,
        "subcategory": "contact",
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
        "subcategory": "general",
        "description": "settingDesc.APP_BASE_URL",
        "default": "",
        "frontend_visible": True,
    },
    "DEBUG": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.AGENT,
        "subcategory": "general",
        "description": "settingDesc.DEBUG",
        "default": False,
    },
    "LOG_LEVEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.AGENT,
        "subcategory": "general",
        "description": "settingDesc.LOG_LEVEL",
        "default": "INFO",
    },
    # ============================================
    # LLM Settings
    # ============================================
    "LLM_MAX_RETRIES": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "subcategory": "retry",
        "description": "settingDesc.LLM_MAX_RETRIES",
        "default": 3,
    },
    "LLM_RETRY_DELAY": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "subcategory": "retry",
        "description": "settingDesc.LLM_RETRY_DELAY",
        "default": 1.0,
    },
    "LLM_MODEL_CACHE_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "subcategory": "cache",
        "description": "settingDesc.LLM_MODEL_CACHE_SIZE",
        "default": 50,
    },
    # ============================================
    # Session Settings
    # ============================================
    "SESSION_MAX_RUNS_PER_SESSION": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "general",
        "description": "settingDesc.SESSION_MAX_RUNS_PER_SESSION",
        "default": 100,
    },
    "ENABLE_MESSAGE_HISTORY": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SESSION,
        "subcategory": "general",
        "description": "settingDesc.ENABLE_MESSAGE_HISTORY",
        "default": True,
    },
    "SSE_CACHE_TTL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "general",
        "description": "settingDesc.SSE_CACHE_TTL",
        "default": 3600,
    },
    "SESSION_TITLE_MODEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "subcategory": "title",
        "description": "settingDesc.SESSION_TITLE_MODEL",
        "default": "claude-3-5-haiku-20241022",
    },
    "SESSION_TITLE_API_BASE": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "subcategory": "title",
        "description": "settingDesc.SESSION_TITLE_API_BASE",
        "default": "",
    },
    "SESSION_TITLE_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "subcategory": "title",
        "description": "settingDesc.SESSION_TITLE_API_KEY",
        "default": "",
        "is_sensitive": True,
    },
    "SESSION_TITLE_PROMPT": {
        "type": SettingType.TEXT,
        "category": SettingCategory.SESSION,
        "subcategory": "title",
        "description": "settingDesc.SESSION_TITLE_PROMPT",
        "default": "请您用简短的3-5个字的标题加上一个表情符号作为用户对话的提示标题。请您选取适合用于总结的表情符号来增强理解，但请避免使用符号或特殊格式。请您根据提示回复一个提示标题文本。\n\n回复示例：\n\n📉 股市趋势\n\n🍪 完美巧克力曲奇食谱\n\n🎮 视频游戏开发洞察\n\n# 重要\n\n1. 请务必用{lang}回复我\n2. 回复字数控制在3-5个字\n\nPrompt: {message}",
    },
    # ============================================
    # Event Merger Settings
    # ============================================
    "ENABLE_EVENT_MERGER": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
        "description": "settingDesc.ENABLE_EVENT_MERGER",
        "default": True,
        "frontend_visible": True,
    },
    "EVENT_MERGE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
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
        "subcategory": "general",
        "description": "settingDesc.ENABLE_SANDBOX",
        "default": False,
        "frontend_visible": True,
    },
    "SANDBOX_PLATFORM": {
        "type": SettingType.SELECT,
        "category": SettingCategory.SANDBOX,
        "subcategory": "general",
        "description": "settingDesc.SANDBOX_PLATFORM",
        "default": "daytona",
        "depends_on": "ENABLE_SANDBOX",
        "options": ["daytona", "e2b"],
    },
    "DAYTONA_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "subcategory": "daytona",
        "description": "settingDesc.DAYTONA_API_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_SERVER_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "subcategory": "daytona",
        "description": "settingDesc.DAYTONA_SERVER_URL",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_TIMEOUT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "subcategory": "daytona",
        "description": "settingDesc.DAYTONA_TIMEOUT",
        "default": 180,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_IMAGE": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "subcategory": "daytona",
        "description": "settingDesc.DAYTONA_IMAGE",
        "default": "",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_AUTO_STOP_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "subcategory": "daytona",
        "description": "settingDesc.DAYTONA_AUTO_STOP_INTERVAL",
        "default": 5,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_AUTO_ARCHIVE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "subcategory": "daytona",
        "description": "settingDesc.DAYTONA_AUTO_ARCHIVE_INTERVAL",
        "default": 5,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "DAYTONA_AUTO_DELETE_INTERVAL": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "subcategory": "daytona",
        "description": "settingDesc.DAYTONA_AUTO_DELETE_INTERVAL",
        "default": 1440,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "daytona"},
    },
    "E2B_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "subcategory": "e2b",
        "description": "settingDesc.E2B_API_KEY",
        "default": "",
        "is_sensitive": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_TEMPLATE": {
        "type": SettingType.STRING,
        "category": SettingCategory.SANDBOX,
        "subcategory": "e2b",
        "description": "settingDesc.E2B_TEMPLATE",
        "default": "base",
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_TIMEOUT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SANDBOX,
        "subcategory": "e2b",
        "description": "settingDesc.E2B_TIMEOUT",
        "default": 3600,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_AUTO_PAUSE": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SANDBOX,
        "subcategory": "e2b",
        "description": "settingDesc.E2B_AUTO_PAUSE",
        "default": True,
        "depends_on": {"key": "SANDBOX_PLATFORM", "value": "e2b"},
    },
    "E2B_AUTO_RESUME": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SANDBOX,
        "subcategory": "e2b",
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
        "subcategory": "general",
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
        "subcategory": "mcp",
        "description": "settingDesc.ENABLE_MCP",
        "default": True,
        "frontend_visible": True,
    },
    "ENABLE_DEFERRED_TOOL_LOADING": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.TOOLS,
        "subcategory": "mcp",
        "description": "settingDesc.ENABLE_DEFERRED_TOOL_LOADING",
        "default": True,
        "depends_on": "ENABLE_MCP",
        "frontend_visible": True,
    },
    "DEFERRED_TOOL_THRESHOLD": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.TOOLS,
        "subcategory": "deferred",
        "description": "settingDesc.DEFERRED_TOOL_THRESHOLD",
        "default": 20,
        "depends_on": "ENABLE_DEFERRED_TOOL_LOADING",
    },
    "DEFERRED_TOOL_SEARCH_LIMIT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.TOOLS,
        "subcategory": "deferred",
        "description": "settingDesc.DEFERRED_TOOL_SEARCH_LIMIT",
        "default": 25,
        "depends_on": "ENABLE_DEFERRED_TOOL_LOADING",
    },
    # ============================================
    # MongoDB Settings
    # ============================================
    "MONGODB_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.MONGODB,
        "subcategory": "connection",
        "description": "settingDesc.MONGODB_URL",
        "default": "mongodb://localhost:27017",
        "is_sensitive": True,
    },
    "MONGODB_DB": {
        "type": SettingType.STRING,
        "category": SettingCategory.MONGODB,
        "subcategory": "connection",
        "description": "settingDesc.MONGODB_DB",
        "default": "agent_state",
    },
    "MONGODB_USERNAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.MONGODB,
        "subcategory": "connection",
        "description": "settingDesc.MONGODB_USERNAME",
        "default": "",
    },
    "MONGODB_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.MONGODB,
        "subcategory": "connection",
        "description": "settingDesc.MONGODB_PASSWORD",
        "default": "",
        "is_sensitive": True,
    },
    "MONGODB_AUTH_SOURCE": {
        "type": SettingType.STRING,
        "category": SettingCategory.MONGODB,
        "subcategory": "connection",
        "description": "settingDesc.MONGODB_AUTH_SOURCE",
        "default": "admin",
    },
    # ============================================
    # Redis Settings
    # ============================================
    "REDIS_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.REDIS,
        "subcategory": "connection",
        "description": "settingDesc.REDIS_URL",
        "default": "redis://localhost:6379/0",
        "is_sensitive": True,
    },
    "REDIS_PASSWORD": {
        "type": SettingType.STRING,
        "category": SettingCategory.REDIS,
        "subcategory": "connection",
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
        "subcategory": "langsmith",
        "description": "settingDesc.LANGSMITH_TRACING",
        "default": False,
    },
    "LANGSMITH_API_KEY": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "subcategory": "langsmith",
        "description": "settingDesc.LANGSMITH_API_KEY",
        "default": "",
        "depends_on": "LANGSMITH_TRACING",
        "is_sensitive": True,
    },
    "LANGSMITH_PROJECT": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "subcategory": "langsmith",
        "description": "settingDesc.LANGSMITH_PROJECT",
        "default": "lamb-agent",
        "depends_on": "LANGSMITH_TRACING",
    },
    "LANGSMITH_API_URL": {
        "type": SettingType.STRING,
        "category": SettingCategory.TRACING,
        "subcategory": "langsmith",
        "description": "settingDesc.LANGSMITH_API_URL",
        "default": "https://api.smith.langchain.com",
        "depends_on": "LANGSMITH_TRACING",
    },
    "LANGSMITH_SAMPLE_RATE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.TRACING,
        "subcategory": "langsmith",
        "description": "settingDesc.LANGSMITH_SAMPLE_RATE",
        "default": 1.0,
        "depends_on": "LANGSMITH_TRACING",
    },
}

# Merge extra definitions (security, storage, user, memory)
SETTING_DEFINITIONS.update(EXTRA_SETTING_DEFINITIONS)
