import pytest

from src.kernel.config import SETTING_DEFINITIONS, Settings


@pytest.mark.parametrize("prefix", ["IMAGE", "VIDEO"])
def test_media_timeout_defaults_are_configurable_ten_minutes(prefix):
    key = f"{prefix}_ANALYSIS_TIMEOUT_SECONDS"
    definition = SETTING_DEFINITIONS[key]
    assert getattr(Settings(), key) == definition["default"] == 600
    assert definition["min_value"] == 1
    assert definition["max_value"] == 3600
    assert definition["frontend_visible"] is True


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("FILE_UPLOAD_MAX_SIZE_IMAGE", 100),
        ("FILE_UPLOAD_MAX_SIZE_VIDEO", 200),
        ("VIDEO_ANALYSIS_MAX_BYTES", 200 * 1024 * 1024),
    ],
)
def test_media_size_defaults_match_admin_settings(key, expected):
    assert getattr(Settings(), key) == SETTING_DEFINITIONS[key]["default"] == expected
