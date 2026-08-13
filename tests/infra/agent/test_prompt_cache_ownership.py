from pathlib import Path

from langchain_anthropic.middleware import AnthropicPromptCachingMiddleware

from src.agents.core import persona

ROOT = Path(__file__).resolve().parents[3]


def _source(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_deepagents_official_anthropic_cache_middleware_is_not_excluded() -> None:
    profile = persona._build_harness_profile()

    assert AnthropicPromptCachingMiddleware not in profile.excluded_middleware


def test_lambchat_does_not_own_prompt_cache_middleware() -> None:
    custom_middleware = ROOT / "src/infra/agent/middleware/prompt_caching.py"
    ownership_sources = (
        "src/infra/agent/middleware/__init__.py",
        "src/agents/fast_agent/nodes.py",
        "src/agents/search_agent/nodes.py",
        "src/agents/team_agent/nodes.py",
    )

    assert not custom_middleware.exists()
    for path in ownership_sources:
        assert "PromptCachingMiddleware" not in _source(path), path


def test_tool_search_does_not_add_lambchat_prompt_cache_markers() -> None:
    source = _source("src/infra/agent/middleware/tool_interception.py")

    assert "_lambchat_prompt_cache_volatile" not in source
