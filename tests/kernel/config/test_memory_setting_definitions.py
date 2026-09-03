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
    # 相关记忆不再自动注入用户消息；索引由 NATIVE_MEMORY_INDEX_ENABLED 控制，
    # 并只附着到 memory_recall 工具描述。
    assert Settings(_env_file=None).NATIVE_MEMORY_QUERY_CONTEXT_ENABLED is False
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_QUERY_CONTEXT_ENABLED"]["default"] is False
    assert Settings(_env_file=None).NATIVE_MEMORY_QUERY_CONTEXT_TOP_K == 3
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_QUERY_CONTEXT_TOP_K"]["default"] == 3
    assert Settings(_env_file=None).NATIVE_MEMORY_QUERY_CONTEXT_MAX_CHARS == 1200
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_QUERY_CONTEXT_MAX_CHARS"]["default"] == 1200


def test_memory_extraction_defaults_match_definitions() -> None:
    expected = {
        "MEMORY_EXTRACTION_ENABLED": True,
        "MEMORY_EXTRACTION_IDLE_SECONDS": 1800,
        "MEMORY_EXTRACTION_MAX_AGE_DAYS": 30,
        "MEMORY_EXTRACTION_MAX_SESSIONS_PER_PASS": 3,
        "MEMORY_EXTRACTION_MAX_ATTEMPTS": 3,
        "MEMORY_EXTRACTION_TRANSCRIPT_MAX_CHARS": 24_000,
        "MEMORY_EXTRACTION_INTERVAL_SECONDS": 900,
    }

    configured = Settings(_env_file=None)
    for name, value in expected.items():
        assert getattr(configured, name) == value
        assert SETTING_DEFINITIONS[name]["default"] == value
        assert SETTING_DEFINITIONS[name]["depends_on"] == "ENABLE_MEMORY"


def test_memory_auto_retain_daily_limit_default_matches_definition() -> None:
    definition = SETTING_DEFINITIONS["NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY"]

    assert Settings(_env_file=None).NATIVE_MEMORY_MAX_AUTO_RETAIN_PER_DAY == 20
    assert definition["default"] == 20


def test_memory_vfs_setting_default_matches_definition() -> None:
    definition = SETTING_DEFINITIONS["ENABLE_MEMORY_VFS"]

    assert Settings(_env_file=None).ENABLE_MEMORY_VFS is False
    assert definition["default"] is False
    assert definition["depends_on"] == "ENABLE_MEMORY"


def test_memory_vector_backend_defaults_match_definitions() -> None:
    assert Settings(_env_file=None).NATIVE_MEMORY_VECTOR_BACKEND == "mongo"
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_VECTOR_BACKEND"]["default"] == "mongo"
    assert Settings(_env_file=None).NATIVE_MEMORY_QDRANT_URL == "http://127.0.0.1:6333"
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_QDRANT_URL"]["default"] == "http://127.0.0.1:6333"
    assert Settings(_env_file=None).NATIVE_MEMORY_QDRANT_API_KEY == ""
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_QDRANT_API_KEY"]["default"] == ""


def test_memory_self_evolve_defaults_match_definitions() -> None:
    assert Settings(_env_file=None).NATIVE_MEMORY_SELF_EVOLVE_ENABLED is False
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_SELF_EVOLVE_ENABLED"]["default"] is False
    assert Settings(_env_file=None).NATIVE_MEMORY_SELF_EVOLVE_MAX_PER_NIGHT == 3
    assert SETTING_DEFINITIONS["NATIVE_MEMORY_SELF_EVOLVE_MAX_PER_NIGHT"]["default"] == 3
