import re
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
        "src/infra/agent/middleware/prompt_injection.py",
        "src/infra/agent/middleware/__init__.py",
        "src/agents/fast_agent/nodes.py",
        "src/agents/fast_agent/prompt.py",
        "src/agents/search_agent/nodes.py",
        "src/agents/search_agent/prompt.py",
        "src/agents/team_agent/nodes.py",
    )
    cache_shaping_patterns = (
        re.compile(r"KV\s+cache", re.IGNORECASE),
        re.compile(r"cache breakpoints?", re.IGNORECASE),
        re.compile(r"stable\s*→\s*semi-stable\s*→\s*dynamic", re.IGNORECASE),
        re.compile(r"session-static", re.IGNORECASE),
    )

    assert not custom_middleware.exists()
    for path in ownership_sources:
        source = _source(path)
        assert "PromptCachingMiddleware" not in source, path
        assert "VolatileSectionPromptMiddleware" not in source, path
        for pattern in cache_shaping_patterns:
            assert pattern.search(source) is None, (path, pattern.pattern)


def test_tool_search_does_not_add_lambchat_prompt_cache_markers() -> None:
    source = _source("src/infra/agent/middleware/tool_interception.py")

    assert "_lambchat_prompt_cache_volatile" not in source


def test_dynamic_prompt_and_tool_injection_do_not_shape_requests_for_cache_hits() -> None:
    prompt_paths = (
        "src/infra/tool/env_var_prompt.py",
        "src/infra/tool/deferred_manager.py",
        "src/infra/agent/middleware/prompt_injection.py",
        "src/infra/agent/middleware/tool_interception.py",
        "src/infra/agent/middleware/_helpers.py",
        "tests/agents/test_search_agent_lazy_sandbox.py",
        "tests/infra/agent/test_tool_interception_uploads.py",
    )
    forbidden_prompt_shaping = (
        "_append_system_text_blocks",
        "build_env_var_prompt_sections",
        "get_deferred_prompt_blocks",
    )

    violations = []
    for path in prompt_paths:
        source = _source(path)
        for marker in forbidden_prompt_shaping:
            if marker in source:
                violations.append((path, marker))

    assert violations == []

    tool_interception = _source("src/infra/agent/middleware/tool_interception.py")
    assert re.search(r"system prompt tail", tool_interception, re.IGNORECASE) is None

    for path in (
        "src/infra/agent/middleware/_helpers.py",
        "src/infra/agent/middleware/tool_interception.py",
    ):
        assert "_tool_sort_key" not in _source(path), path
