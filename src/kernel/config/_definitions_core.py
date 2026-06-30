"""Core setting definitions: Frontend, Application, LLM, Session, Event Merger."""

from __future__ import annotations

from src.kernel.schemas.setting import (
    JsonSchema,
    JsonSchemaField,
    SettingCategory,
    SettingType,
)

CORE_SETTING_DEFINITIONS: dict[str, dict] = {
    # ============================================
    # Frontend Settings
    # ============================================
    "DEFAULT_AGENT": {
        "type": SettingType.STRING,
        "category": SettingCategory.FRONTEND,
        "subcategory": "display",
        "description": "settingDesc.DEFAULT_AGENT",
        "default": "fast",
        "frontend_visible": True,
    },
    "DEFAULT_MODEL_ID": {
        "type": SettingType.STRING,
        "category": SettingCategory.LLM,
        "subcategory": "model",
        "description": "settingDesc.DEFAULT_MODEL_ID",
        "default": "",
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
                {
                    "icon": "📁",
                    "text": "ワークスペースディレクトリのファイルを一覧表示",
                },
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
                    layout_width="compact",
                ),
                JsonSchemaField(
                    name="text",
                    type="text",
                    label="settingDesc.WELCOME_SUGGESTION_TEXT",
                    placeholder="...",
                    required=True,
                    layout_width="full",
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
    "PROMPT_CACHE_MAX_SYSTEM_BLOCKS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "subcategory": "cache",
        "description": "settingDesc.PROMPT_CACHE_MAX_SYSTEM_BLOCKS",
        "default": 4,
    },
    "PROMPT_CACHE_MAX_TOOLS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.LLM,
        "subcategory": "cache",
        "description": "settingDesc.PROMPT_CACHE_MAX_TOOLS",
        "default": 1,
    },
    # ============================================
    # Session Settings
    # ============================================
    "SESSION_MAX_RUNS_PER_SESSION": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "general",
        "description": "settingDesc.SESSION_MAX_RUNS_PER_SESSION",
        "default": 1000,
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
        "default": 86400,
    },
    "SESSION_EVENT_MONGO_BUFFER_MAX": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
        "description": "settingDesc.SESSION_EVENT_MONGO_BUFFER_MAX",
        "default": 10000,
    },
    "SESSION_EVENT_READ_DEFAULT_LIMIT": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
        "description": "settingDesc.SESSION_EVENT_READ_DEFAULT_LIMIT",
        "default": 1000,
    },
    "SESSION_EVENT_TTL_CACHE_MAX": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
        "description": "settingDesc.SESSION_EVENT_TTL_CACHE_MAX",
        "default": 5000,
    },
    "SESSION_EVENT_REDIS_REPLAY_BATCH_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
        "description": "settingDesc.SESSION_EVENT_REDIS_REPLAY_BATCH_SIZE",
        "default": 500,
    },
    "FEISHU_UPLOAD_BYTES_MAX_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.FILE_UPLOAD,
        "subcategory": "feishu",
        "description": "settingDesc.FEISHU_UPLOAD_BYTES_MAX_SIZE",
        "default": 20971520,
        "frontend_visible": False,
    },
    "SESSION_SEARCH_BACKFILL_STARTUP_DELAY_SECONDS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "general",
        "description": "settingDesc.SESSION_SEARCH_BACKFILL_STARTUP_DELAY_SECONDS",
        "default": 30.0,
    },
    "SESSION_TITLE_MODEL": {
        "type": SettingType.STRING,
        "category": SettingCategory.SESSION,
        "subcategory": "title",
        "description": "settingDesc.SESSION_TITLE_MODEL",
        "default": "",
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
    "ENABLE_RECOMMEND_QUESTIONS": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.SESSION,
        "subcategory": "recommendations",
        "description": "settingDesc.ENABLE_RECOMMEND_QUESTIONS",
        "default": True,
    },
    "RECOMMEND_QUESTIONS_MAX_BACKGROUND_TASKS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "recommendations",
        "description": "settingDesc.RECOMMEND_QUESTIONS_MAX_BACKGROUND_TASKS",
        "default": 8,
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
    "EVENT_MERGE_BATCH_SIZE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
        "description": "settingDesc.EVENT_MERGE_BATCH_SIZE",
        "default": 100,
        "depends_on": "ENABLE_EVENT_MERGER",
    },
    "EVENT_MERGE_CONCURRENCY": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
        "description": "settingDesc.EVENT_MERGE_CONCURRENCY",
        "default": 3,
        "depends_on": "ENABLE_EVENT_MERGER",
    },
    "EVENT_MERGE_TIMEOUT_SECONDS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
        "description": "settingDesc.EVENT_MERGE_TIMEOUT_SECONDS",
        "default": 120.0,
        "depends_on": "ENABLE_EVENT_MERGER",
    },
    "EVENT_MERGE_MAX_EVENTS_PER_TRACE": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.SESSION,
        "subcategory": "events",
        "description": "settingDesc.EVENT_MERGE_MAX_EVENTS_PER_TRACE",
        "default": 5000,
        "depends_on": "ENABLE_EVENT_MERGER",
    },
}
