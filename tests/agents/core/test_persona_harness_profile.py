from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from src.agents.core import persona


def test_harness_profile_keeps_deepagents_anthropic_cache_owner() -> None:
    profile = persona._build_harness_profile()

    assert profile.base_system_prompt == persona._BEHAVIOR_GUIDE
    assert AnthropicPromptCachingMiddleware not in profile.excluded_middleware
