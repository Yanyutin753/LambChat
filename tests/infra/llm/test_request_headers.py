"""Anti-ban default request headers for upstream LLM providers.

OpenAI/Anthropic-protocol clients get opencode/Claude-Code-style default
headers (User-Agent / x-app) so third-party relays that fingerprint official
clients stop flagging LambChat traffic. Google protocol is skipped (its
langchain wrapper has no default_headers support). A JSON setting
(LLM_REQUEST_HEADERS) can override defaults; explicit caller kwargs still win.
"""

import json

import pytest

from src.infra.llm.client import (
    LLMClient,
    _default_request_headers,
    _make_cache_key,
    _merged_request_headers,
    _settings_header_overrides,
)
from src.kernel.config import settings
from src.kernel.config.definitions import SETTING_DEFINITIONS
from src.kernel.config.service import _ALLOW_EMPTY_STRING_SETTINGS


@pytest.fixture(autouse=True)
def _clean_header_setting(monkeypatch):
    monkeypatch.setattr(settings, "LLM_REQUEST_HEADERS", "", raising=False)
    yield


def test_anthropic_defaults_mimic_claude_cli() -> None:
    headers = _default_request_headers("anthropic")
    assert headers["User-Agent"].startswith("claude-cli/")
    assert headers["x-app"] == "cli"


def test_openai_defaults_mimic_opencode() -> None:
    headers = _default_request_headers("openai")
    assert headers["User-Agent"].startswith("opencode/")


def test_google_protocol_has_no_injected_headers() -> None:
    assert _default_request_headers("google") == {}


def test_settings_json_overrides_defaults() -> None:
    settings.LLM_REQUEST_HEADERS = json.dumps({"User-Agent": "my-agent/1.0", "X-Extra": "1"})
    headers = _merged_request_headers("anthropic", {})
    assert headers["User-Agent"] == "my-agent/1.0"
    assert headers["X-Extra"] == "1"
    # 未覆盖的内置键保留
    assert headers["x-app"] == "cli"


def test_invalid_settings_json_falls_back_to_defaults() -> None:
    settings.LLM_REQUEST_HEADERS = "{not json"
    assert _settings_header_overrides() == {}
    headers = _merged_request_headers("anthropic", {})
    assert headers["User-Agent"].startswith("claude-cli/")


def test_caller_default_headers_win_over_defaults() -> None:
    class Omit:
        pass

    omit = Omit()
    headers = _merged_request_headers(
        "anthropic", {"default_headers": {"X-Api-Key": omit, "User-Agent": "custom/2"}}
    )
    assert headers["X-Api-Key"] is omit
    assert headers["User-Agent"] == "custom/2"
    assert headers["x-app"] == "cli"


def test_merged_headers_empty_for_google() -> None:
    assert _merged_request_headers("google", {}) is None


def test_create_anthropic_model_carries_headers() -> None:
    model = LLMClient._create_model(
        "anthropic",
        "claude-sonnet-4-5",
        temperature=0.7,
        api_key="sk-test",
    )
    assert model.default_headers["x-app"] == "cli"
    assert model.default_headers["User-Agent"].startswith("claude-cli/")


def test_create_openai_model_carries_headers() -> None:
    model = LLMClient._create_model(
        "openai",
        "gpt-5.2",
        temperature=0.7,
        api_key="sk-test",
    )
    assert model.default_headers["User-Agent"].startswith("opencode/")


def test_create_google_model_has_no_default_headers_kwarg() -> None:
    model = LLMClient._create_model(
        "google",
        "gemini-2.5-pro",
        temperature=0.7,
        api_key="sk-test",
    )
    assert getattr(model, "default_headers", None) is None


# ── per-model request_headers override ────────────────────────────────────


def test_model_headers_override_settings_and_defaults() -> None:
    settings.LLM_REQUEST_HEADERS = json.dumps({"User-Agent": "global/1"})
    model = LLMClient._create_model(
        "openai",
        "gpt-5.2",
        temperature=0.7,
        api_key="sk-test",
        request_headers={"User-Agent": "per-model/1"},
    )
    assert model.default_headers["User-Agent"] == "per-model/1"


def test_model_headers_merge_with_builtin_defaults() -> None:
    model = LLMClient._create_model(
        "anthropic",
        "claude-sonnet-4-5",
        temperature=0.7,
        api_key="sk-test",
        request_headers={"anthropic-beta": "context-1m-2025-08-07"},
    )
    headers = model.default_headers
    assert headers["anthropic-beta"] == "context-1m-2025-08-07"
    # 未覆盖的内置防封头保留
    assert headers["x-app"] == "cli"
    assert headers["User-Agent"].startswith("claude-cli/")


@pytest.mark.asyncio
async def test_get_model_applies_model_config_request_headers() -> None:
    from src.kernel.schemas.model import ModelConfig

    LLMClient._model_cache.clear()
    try:
        model = await LLMClient.get_model(
            model_config=ModelConfig(
                value="anthropic/claude-sonnet-4-5",
                label="test",
                api_key="sk-test",
                request_headers={"User-Agent": "relay-friendly/3"},
            )
        )
        assert model.default_headers["User-Agent"] == "relay-friendly/3"
    finally:
        LLMClient._model_cache.clear()


# ── settings plumbing ─────────────────────────────────────────────────────


def test_llm_request_headers_setting_is_not_frontend_visible() -> None:
    """Headers may carry relay credentials — must not leak to non-admin users."""
    definition = SETTING_DEFINITIONS["LLM_REQUEST_HEADERS"]
    assert not definition.get("frontend_visible")
    assert definition.get("is_sensitive") is True


def test_llm_request_headers_allows_clearing_back_to_empty() -> None:
    """Default is ""; clearing the setting at runtime must not be a silent no-op."""
    assert "LLM_REQUEST_HEADERS" in _ALLOW_EMPTY_STRING_SETTINGS


# ── cache-key participation ────────────────────────────────────────────────


def test_cache_key_differs_for_different_header_overrides() -> None:
    base = _make_cache_key("openai", "gpt-test", 0.7, None, "sk", None, None, None, 3)
    with_a = _make_cache_key(
        "openai",
        "gpt-test",
        0.7,
        None,
        "sk",
        None,
        None,
        None,
        3,
        header_overrides=(None, (("User-Agent", "a/1"),)),
    )
    with_b = _make_cache_key(
        "openai",
        "gpt-test",
        0.7,
        None,
        "sk",
        None,
        None,
        None,
        3,
        header_overrides=(None, (("User-Agent", "b/1"),)),
    )
    assert base != with_a
    assert with_a != with_b


@pytest.mark.asyncio
async def test_get_model_caches_per_model_headers_separately() -> None:
    from src.kernel.schemas.model import ModelConfig

    LLMClient._model_cache.clear()
    try:
        model_a = await LLMClient.get_model(
            model_config=ModelConfig(
                value="anthropic/claude-sonnet-4-5",
                label="a",
                api_key="sk-test",
                request_headers={"User-Agent": "relay-a/1"},
            )
        )
        model_b = await LLMClient.get_model(
            model_config=ModelConfig(
                value="anthropic/claude-sonnet-4-5",
                label="b",
                api_key="sk-test",
                request_headers={"User-Agent": "relay-b/1"},
            )
        )
        assert model_a is not model_b
        assert model_a.default_headers["User-Agent"] == "relay-a/1"
        assert model_b.default_headers["User-Agent"] == "relay-b/1"
    finally:
        LLMClient._model_cache.clear()
