from __future__ import annotations

from src.kernel.config.base import Settings
from src.kernel.config.definitions import SETTING_DEFINITIONS


def test_memory_auto_capture_task_limit_default_matches_definition() -> None:
    definition = SETTING_DEFINITIONS["NATIVE_MEMORY_AUTO_CAPTURE_MAX_TASKS"]

    assert Settings(_env_file=None).NATIVE_MEMORY_AUTO_CAPTURE_MAX_TASKS == 8
    assert definition["default"] == 8
    assert definition.get("frontend_visible", False) is False


def test_memory_index_cache_ttl_defaults_aligned() -> None:
    definition = SETTING_DEFINITIONS["NATIVE_MEMORY_INDEX_CACHE_TTL"]

    assert Settings(_env_file=None).NATIVE_MEMORY_INDEX_CACHE_TTL == 300
    assert definition["default"] == 300


def test_memory_embedding_dimensions_default_matches_definition() -> None:
    definition = SETTING_DEFINITIONS["NATIVE_MEMORY_EMBEDDING_DIMENSIONS"]

    assert Settings(_env_file=None).NATIVE_MEMORY_EMBEDDING_DIMENSIONS == 1536
    assert definition["default"] == 1536


def test_memory_query_context_defaults_match_definitions() -> None:
    assert Settings(_env_file=None).NATIVE_MEMORY_QUERY_CONTEXT_ENABLED is False
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_QUERY_CONTEXT_ENABLED"]["default"] is False
    assert Settings(_env_file=None).NATIVE_MEMORY_QUERY_CONTEXT_TOP_K == 3
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_QUERY_CONTEXT_TOP_K"]["default"] == 3
    assert Settings(_env_file=None).NATIVE_MEMORY_QUERY_CONTEXT_MAX_CHARS == 1200
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_QUERY_CONTEXT_MAX_CHARS"]["default"] == 1200
