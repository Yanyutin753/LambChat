from pathlib import Path

from src.kernel.config import settings
from src.kernel.config.definitions import SETTING_DEFINITIONS

REMOVED_PROMPT_CACHE_SETTINGS = (
    "PROMPT_CACHE_MAX_SYSTEM_BLOCKS",
    "PROMPT_CACHE_MAX_TOOLS",
)
LLM_ENV_DOCS = (
    Path("docs/en/env/llm.md"),
    Path("docs/zh/env/llm.md"),
)


def test_custom_prompt_cache_settings_are_removed_from_live_configuration() -> None:
    for setting_name in REMOVED_PROMPT_CACHE_SETTINGS:
        assert not hasattr(settings, setting_name)
        assert setting_name not in SETTING_DEFINITIONS

        for doc_path in LLM_ENV_DOCS:
            assert setting_name not in doc_path.read_text()
