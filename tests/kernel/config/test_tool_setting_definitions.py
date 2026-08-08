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
