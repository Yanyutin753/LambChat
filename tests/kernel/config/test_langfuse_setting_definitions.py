from __future__ import annotations

"""Langfuse 追踪设置定义：镜像 LangSmith 的模式，密钥标记敏感。"""

from src.kernel.config.base import Settings
from src.kernel.config.definitions import SETTING_DEFINITIONS


def test_langfuse_setting_definitions_exist() -> None:
    for key in ("LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        assert key in SETTING_DEFINITIONS, key


def test_langfuse_definitions_categorized_under_tracing() -> None:
    for key in ("LANGFUSE_ENABLED", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"):
        definition = SETTING_DEFINITIONS[key]
        assert definition["category"].value == "tracing", key
        assert definition["subcategory"] == "langfuse", key


def test_langfuse_keys_are_sensitive() -> None:
    assert SETTING_DEFINITIONS["LANGFUSE_PUBLIC_KEY"]["is_sensitive"] is True
    assert SETTING_DEFINITIONS["LANGFUSE_SECRET_KEY"]["is_sensitive"] is True


def test_langfuse_defaults_match_settings_fields() -> None:
    assert Settings().LANGFUSE_ENABLED is False
    assert SETTING_DEFINITIONS["LANGFUSE_ENABLED"]["default"] is False
    assert SETTING_DEFINITIONS["LANGFUSE_HOST"]["default"] == "http://localhost:3000"
