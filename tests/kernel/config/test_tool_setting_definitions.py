from src.kernel.config._definitions_tools import TOOLS_SETTING_DEFINITIONS
from src.kernel.config.base import Settings


def test_skill_prompt_description_threshold_is_registered() -> None:
    field = Settings.model_fields["SKILL_PROMPT_DESCRIPTION_THRESHOLD"]
    definition = TOOLS_SETTING_DEFINITIONS["SKILL_PROMPT_DESCRIPTION_THRESHOLD"]

    assert field.default == 20
    assert definition["default"] == 20
    assert definition["depends_on"] == "ENABLE_SKILLS"


def test_removed_deferred_prompt_limit_is_not_registered() -> None:
    assert "DEFERRED_TOOL_PROMPT_LIMIT" not in Settings.model_fields
    assert "DEFERRED_TOOL_PROMPT_LIMIT" not in TOOLS_SETTING_DEFINITIONS


def test_web_search_settings_are_registered() -> None:
    expected_defaults = {
        # 默认挂载为系统内置工具（未配 provider 时工具自述引导，而非不挂载）
        "ENABLE_WEB_SEARCH": True,
        "WEB_SEARCH_PROVIDER": "auto",
        "TAVILY_API_KEYS": "",
        "BRAVE_API_KEYS": "",
        "SEARXNG_BASE_URL": "",
        "SEARXNG_API_KEY": "",
    }
    for key, default in expected_defaults.items():
        assert Settings.model_fields[key].default == default
        assert TOOLS_SETTING_DEFINITIONS[key]["default"] == default

    assert TOOLS_SETTING_DEFINITIONS["WEB_SEARCH_PROVIDER"]["options"] == [
        "auto",
        "tavily",
        "brave",
        "searxng",
    ]
    assert TOOLS_SETTING_DEFINITIONS["TAVILY_API_KEYS"]["is_sensitive"] is True
    assert TOOLS_SETTING_DEFINITIONS["BRAVE_API_KEYS"]["is_sensitive"] is True
    assert TOOLS_SETTING_DEFINITIONS["SEARXNG_API_KEY"]["is_sensitive"] is True
    assert TOOLS_SETTING_DEFINITIONS["SEARXNG_BASE_URL"].get("is_sensitive") is not True
    for key in expected_defaults:
        if key != "ENABLE_WEB_SEARCH":
            assert TOOLS_SETTING_DEFINITIONS[key]["depends_on"] == "ENABLE_WEB_SEARCH"


def test_web_fetch_settings_are_registered() -> None:
    expected_defaults = {
        # 默认挂载（direct 供应商零 key 可用）
        "ENABLE_WEB_FETCH": True,
        "WEB_FETCH_PROVIDER": "auto",
        "JINA_API_KEYS": "",
        "FIRECRAWL_BASE_URL": "",
        "FIRECRAWL_API_KEYS": "",
        "EXA_API_KEYS": "",
        "WEB_FETCH_MAX_CHARS": 32768,
    }
    for key, default in expected_defaults.items():
        assert Settings.model_fields[key].default == default
        assert TOOLS_SETTING_DEFINITIONS[key]["default"] == default

    assert TOOLS_SETTING_DEFINITIONS["WEB_FETCH_PROVIDER"]["options"] == [
        "auto",
        "direct",
        "tavily",
        "firecrawl",
        "exa",
        "jina",
    ]
    assert TOOLS_SETTING_DEFINITIONS["FIRECRAWL_API_KEYS"]["is_sensitive"] is True
    assert TOOLS_SETTING_DEFINITIONS["EXA_API_KEYS"]["is_sensitive"] is True
    assert TOOLS_SETTING_DEFINITIONS["FIRECRAWL_BASE_URL"].get("is_sensitive") is not True
    assert TOOLS_SETTING_DEFINITIONS["JINA_API_KEYS"]["is_sensitive"] is True
    for key in expected_defaults:
        if key != "ENABLE_WEB_FETCH":
            assert TOOLS_SETTING_DEFINITIONS[key]["depends_on"] == "ENABLE_WEB_FETCH"


def test_video_analysis_settings_suite_is_registered() -> None:
    """一工具一套：视频分析有独立的模型/重试/字节上限设置（未配模型回落图片的）。"""
    expected = {
        "VIDEO_ANALYSIS_MODEL_ID": "",
        "VIDEO_ANALYSIS_MAX_ATTEMPTS": 3,
        "VIDEO_ANALYSIS_RETRY_DELAY": 1.0,
        "VIDEO_ANALYSIS_MAX_BYTES": 52428800,
    }
    for key, default in expected.items():
        assert Settings.model_fields[key].default == default, key
        assert TOOLS_SETTING_DEFINITIONS[key]["default"] == default, key
        assert TOOLS_SETTING_DEFINITIONS[key]["subcategory"] == "video_analysis", key
        assert TOOLS_SETTING_DEFINITIONS[key]["depends_on"] == "ENABLE_IMAGE_ANALYSIS", key
    assert TOOLS_SETTING_DEFINITIONS["VIDEO_ANALYSIS_MAX_BYTES"]["min_value"] == 1048576
    assert TOOLS_SETTING_DEFINITIONS["VIDEO_ANALYSIS_MAX_BYTES"]["max_value"] == 209715200
