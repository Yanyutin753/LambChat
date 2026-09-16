from __future__ import annotations

import pytest

from src.kernel.config.base import Settings
from src.kernel.config.definitions import SETTING_DEFINITIONS


def test_session_event_settings_default_to_conservative_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # _env_file=None skips .env but inherited process values still take precedence.
    for key in (
        "SSE_CACHE_TTL",
        "SESSION_MAX_EVENTS_PER_TRACE",
        "SESSION_EVENT_READ_DEFAULT_LIMIT",
        "SESSION_EVENT_MONGO_BUFFER_MAX",
        "SESSION_EVENT_TTL_CACHE_MAX",
        "SESSION_EVENT_REDIS_REPLAY_BATCH_SIZE",
        "SESSION_EVENT_CHUNK_STORAGE_ENABLED",
        "SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY",
        "SESSION_EVENT_CHUNK_SIZE",
        "MONGODB_TRACE_EVENT_CHUNKS_COLLECTION",
    ):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)

    assert settings.SSE_CACHE_TTL == 24 * 60 * 60
    assert settings.SESSION_MAX_EVENTS_PER_TRACE == 50000
    assert settings.SESSION_EVENT_READ_DEFAULT_LIMIT == 1000
    assert settings.SESSION_EVENT_MONGO_BUFFER_MAX == 10000
    assert settings.SESSION_EVENT_TTL_CACHE_MAX == 5000
    assert settings.SESSION_EVENT_REDIS_REPLAY_BATCH_SIZE == 500
    assert settings.SESSION_EVENT_CHUNK_STORAGE_ENABLED is False
    assert settings.SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY is False
    assert settings.SESSION_EVENT_CHUNK_SIZE == 5000
    assert settings.MONGODB_TRACE_EVENT_CHUNKS_COLLECTION == "trace_event_chunks"


def test_session_event_setting_definitions_match_runtime_defaults() -> None:
    assert SETTING_DEFINITIONS["SSE_CACHE_TTL"]["default"] == 24 * 60 * 60
    assert SETTING_DEFINITIONS["SESSION_EVENT_READ_DEFAULT_LIMIT"]["default"] == 1000
    assert SETTING_DEFINITIONS["SESSION_EVENT_MONGO_BUFFER_MAX"]["default"] == 10000
    assert SETTING_DEFINITIONS["SESSION_EVENT_TTL_CACHE_MAX"]["default"] == 5000
    assert SETTING_DEFINITIONS["SESSION_EVENT_REDIS_REPLAY_BATCH_SIZE"]["default"] == 500
    assert SETTING_DEFINITIONS["SESSION_EVENT_CHUNK_STORAGE_ENABLED"]["default"] is False
    assert SETTING_DEFINITIONS["SESSION_EVENT_CHUNK_DUAL_WRITE_LEGACY"]["default"] is False
    assert SETTING_DEFINITIONS["SESSION_EVENT_CHUNK_SIZE"]["default"] == 5000
