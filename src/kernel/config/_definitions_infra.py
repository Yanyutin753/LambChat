"""Infrastructure setting definitions: MongoDB, Redis, Task Backend, LangSmith Tracing."""

from __future__ import annotations

from src.kernel.schemas.setting import SettingCategory, SettingType

INFRA_SETTING_DEFINITIONS: dict[str, dict] = {
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
    "MONGODB_STORE_BATCH_CONCURRENCY": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.MONGODB,
        "subcategory": "performance",
        "description": "settingDesc.MONGODB_STORE_BATCH_CONCURRENCY",
        "default": 16,
        "frontend_visible": False,
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
    "TASK_BACKEND": {
        "type": SettingType.SELECT,
        "category": SettingCategory.REDIS,
        "subcategory": "task",
        "description": "settingDesc.TASK_BACKEND",
        "default": "arq",
        "options": ["local", "arq"],
    },
    "ARQ_EMBEDDED_WORKER": {
        "type": SettingType.BOOLEAN,
        "category": SettingCategory.REDIS,
        "subcategory": "task",
        "description": "settingDesc.ARQ_EMBEDDED_WORKER",
        "default": True,
        "depends_on": {"key": "TASK_BACKEND", "value": "arq"},
    },
    "ARQ_QUEUE_NAME": {
        "type": SettingType.STRING,
        "category": SettingCategory.REDIS,
        "subcategory": "task",
        "description": "settingDesc.ARQ_QUEUE_NAME",
        "default": "lambchat:arq",
        "depends_on": {"key": "TASK_BACKEND", "value": "arq"},
    },
    "ARQ_WORKER_MAX_JOBS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.REDIS,
        "subcategory": "task",
        "description": "settingDesc.ARQ_WORKER_MAX_JOBS",
        "default": 128,
        "depends_on": {"key": "TASK_BACKEND", "value": "arq"},
    },
    "ARQ_JOB_TIMEOUT_SECONDS": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.REDIS,
        "subcategory": "task",
        "description": "settingDesc.ARQ_JOB_TIMEOUT_SECONDS",
        "default": 86400,
        "depends_on": {"key": "TASK_BACKEND", "value": "arq"},
    },
    "TASK_STARTUP_CLEANUP_CONCURRENCY": {
        "type": SettingType.NUMBER,
        "category": SettingCategory.REDIS,
        "subcategory": "task",
        "description": "settingDesc.TASK_STARTUP_CLEANUP_CONCURRENCY",
        "default": 16,
        "depends_on": {"key": "TASK_BACKEND", "value": "arq"},
        "frontend_visible": False,
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
