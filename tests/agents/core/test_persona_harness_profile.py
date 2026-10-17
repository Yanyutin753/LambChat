from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from src.agents.core import persona


def test_harness_profile_keeps_deepagents_anthropic_cache_owner() -> None:
    profile = persona._build_harness_profile()

    assert profile.base_system_prompt == persona._BEHAVIOR_GUIDE
    assert AnthropicPromptCachingMiddleware not in profile.excluded_middleware


def test_guarantee_review_reaches_runtime_and_quick_prompts_without_duplication() -> None:
    from src.agents.core.subagent_prompts import (
        DETAILED_SUBAGENT_READ_ONLY_PROMPT,
        MAIN_AGENT_PROMPT_SECTIONS,
        SUBAGENT_PROMPT,
    )
    from src.agents.quick_agent.prompt import QUICK_SYSTEM_PROMPT

    profile_prompt = persona._build_harness_profile().base_system_prompt
    effective_prompts = (
        "\n\n".join((profile_prompt, *MAIN_AGENT_PROMPT_SECTIONS)),
        "\n\n".join((profile_prompt, SUBAGENT_PROMPT)),
        "\n\n".join((profile_prompt, DETAILED_SUBAGENT_READ_ONLY_PROMPT)),
        QUICK_SYSTEM_PROMPT,
    )
    for prompt in effective_prompts:
        assert prompt.count("adversarial counterexamples") == 1
        assert "necessary from sufficient conditions" in prompt
