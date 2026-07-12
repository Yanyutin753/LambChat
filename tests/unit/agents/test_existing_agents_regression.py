"""Verify that fast_agent and search_agent still register correctly after adding team agent."""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.agents.core.base import _AGENT_REGISTRY

# ---------------------------------------------------------------------------
# Helpers: mock heavy external dependencies so agent modules can load
# ---------------------------------------------------------------------------

_DEEPAGENTS_SUBMODULES = [
    "deepagents",
    "deepagents.backends",
    "deepagents.backends.protocol",
    "deepagents.backends.sandbox",
    "deepagents.backends.utils",
    "deepagents.middleware",
    "deepagents.middleware.subagents",
    "deepagents.middleware.summarization",
]

_EXTERNAL_PACKAGES = [
    "arq",
    "arq.connections",
    "arq.jobs",
]


def _install_package_mock(name: str) -> MagicMock:
    """Create and register a mock module for an external package."""
    mod = MagicMock()
    mod.__path__ = [name.replace(".", "/")]
    mod.__package__ = name
    mod.__spec__ = MagicMock()
    sys.modules[name] = mod
    return mod


def _install_deepagents_mocks():
    """Install deepagents mocks with a real dataclass for ReadResult."""
    root = _install_package_mock("deepagents")

    for mod_path in _DEEPAGENTS_SUBMODULES[1:]:
        parts = mod_path.split(".")
        node = root
        for part in parts[1:]:
            node = getattr(node, part)
        node.__path__ = [mod_path.replace(".", "/")]
        node.__package__ = mod_path.rsplit(".", 1)[0]
        node.__spec__ = MagicMock()
        sys.modules[mod_path] = node

    @dataclass
    class _MockReadResult:
        file_data: dict = field(default_factory=dict)
        error: str | None = None

    sys.modules["deepagents.backends.protocol"].ReadResult = _MockReadResult


def _install_external_mocks():
    """Mock all third-party packages that the import chain requires."""
    for pkg in _EXTERNAL_PACKAGES:
        _install_package_mock(pkg)


def _remove_mock_modules():
    """Remove all mock modules from sys.modules."""
    prefixes = tuple(_DEEPAGENTS_SUBMODULES) + tuple(_EXTERNAL_PACKAGES)
    for key in list(sys.modules.keys()):
        if key in prefixes or any(
            key.startswith(p + ".") for p in (*_DEEPAGENTS_SUBMODULES, *_EXTERNAL_PACKAGES)
        ):
            del sys.modules[key]


def _unload_test_subjects():
    """Unload agent and infra modules for test isolation."""
    prefixes = (
        "src.agents.fast_agent",
        "src.agents.search_agent",
        "plugins.system.agent_team.backend.runtime",
        "src.agents.core.persona",
        "src.infra.backend",
        "src.infra.llm",
        "src.infra.sandbox",
        "src.infra.sandbox_grep",
        "src.infra.tool",
        "src.infra.skill",
        "src.infra.memory",
        "src.infra.task",
    )
    for key in list(sys.modules.keys()):
        if any(key == p or key.startswith(p + ".") for p in prefixes):
            del sys.modules[key]


@pytest.fixture(autouse=True)
def _mock_heavy_deps():
    """Mock heavy external dependencies so agent modules can load in test env."""
    _install_deepagents_mocks()
    _install_external_mocks()
    yield
    from src.agents import set_plugin_runtime

    set_plugin_runtime(None)
    _unload_test_subjects()
    _remove_mock_modules()


# ---------------------------------------------------------------------------
# Registration tests
# ---------------------------------------------------------------------------


def test_fast_agent_registered():
    from src.agents import discover_agents

    discover_agents()
    assert "fast" in _AGENT_REGISTRY


def test_search_agent_registered():
    from src.agents import discover_agents

    discover_agents()
    assert "search" in _AGENT_REGISTRY


def test_team_agent_registered():
    from src.agents import discover_agents, set_plugin_runtime
    from src.kernel.extensions import AGENT_TEAM_PLUGIN_ID, BUILTIN_PLUGIN_MANIFESTS, PluginRuntime

    _AGENT_REGISTRY.pop("team", None)
    manifest = next(
        plugin for plugin in BUILTIN_PLUGIN_MANIFESTS if plugin.id == AGENT_TEAM_PLUGIN_ID
    )
    set_plugin_runtime(PluginRuntime([manifest]))
    discover_agents()
    assert "team" in _AGENT_REGISTRY


def test_team_agent_source_directory_removed():
    assert not Path("src/agents/team_agent").exists()


# ---------------------------------------------------------------------------
# Prompt regression tests
# ---------------------------------------------------------------------------


def test_subagent_prompt_unchanged():
    from src.agents.core.subagent_prompts import DEFAULT_SUBAGENT_PROMPT, SUBAGENT_PROMPT

    assert "Handoff Notes" in SUBAGENT_PROMPT
    assert "Handoff Notes" in DEFAULT_SUBAGENT_PROMPT


def test_main_agent_prompt_sections_unchanged():
    from src.agents.core.subagent_prompts import MAIN_AGENT_PROMPT_SECTIONS

    assert any("task" in str(s).lower() for s in MAIN_AGENT_PROMPT_SECTIONS)
    assert "Handoff Notes" not in str(MAIN_AGENT_PROMPT_SECTIONS)


def test_shared_agent_prompts_include_privacy_output_policy():
    from src.agents.core.subagent_prompts import MAIN_AGENT_PROMPT_SECTIONS, SUBAGENT_PROMPT

    combined_prompt = "\n".join((*MAIN_AGENT_PROMPT_SECTIONS, SUBAGENT_PROMPT))

    assert "Privacy-Safe Output" in combined_prompt
    assert "Do not repeat sensitive personal data" in combined_prompt
    assert "access tokens" in combined_prompt


def test_build_role_subagent_prompt_exists():
    from src.agents.core.subagent_prompts import build_role_subagent_prompt

    prompt = build_role_subagent_prompt(
        role_name="Test",
        role_system_prompt="You test things.",
    )
    assert "Test" in prompt
    assert "Handoff Notes" in prompt
