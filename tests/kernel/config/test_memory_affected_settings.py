from __future__ import annotations

from src.kernel.config.service import MEMORY_AFFECTED_SETTINGS


def test_memory_affected_settings_cover_embedding_config() -> None:
    assert "ENABLE_MEMORY" in MEMORY_AFFECTED_SETTINGS
    assert "NATIVE_MEMORY_EMBEDDING_API_BASE" in MEMORY_AFFECTED_SETTINGS
    assert "NATIVE_MEMORY_EMBEDDING_API_KEY" in MEMORY_AFFECTED_SETTINGS
    # 换 embedding 模型 = 换 embed client，必须触发 backend 重建
    assert "NATIVE_MEMORY_EMBEDDING_MODEL" in MEMORY_AFFECTED_SETTINGS
