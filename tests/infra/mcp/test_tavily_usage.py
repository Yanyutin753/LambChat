from __future__ import annotations

import pytest


def test_resolve_context_prefers_explicit_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.mcp.tavily_usage import resolve_tavily_context
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TAVILY_USAGE_API_KEY", "tvly-explicit", raising=False)

    context = resolve_tavily_context(
        "tavily",
        {"url": "https://mcp.tavily.com/mcp?tavilyApiKey=tvly-url"},
    )

    assert context is not None
    assert context.api_key.get_secret_value() == "tvly-explicit"
    assert len(context.credential_fingerprint) == 64
    assert "explicit" not in context.credential_fingerprint


@pytest.mark.parametrize(
    ("server_name", "config", "expected_key"),
    [
        (
            "tavily",
            {"url": "https://mcp.tavily.com/mcp?tavilyApiKey=tvly-url"},
            "tvly-url",
        ),
        (
            "search",
            {
                "url": "https://api.tavily.com/mcp",
                "headers": {"Authorization": "Bearer tvly-header"},
            },
            "tvly-header",
        ),
    ],
)
def test_resolve_context_accepts_trusted_tavily_sources(
    monkeypatch: pytest.MonkeyPatch,
    server_name: str,
    config: dict[str, object],
    expected_key: str,
) -> None:
    from src.infra.mcp.tavily_usage import resolve_tavily_context
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TAVILY_USAGE_API_KEY", "", raising=False)

    context = resolve_tavily_context(server_name, config)

    assert context is not None
    assert context.api_key.get_secret_value() == expected_key


@pytest.mark.parametrize(
    "config",
    [
        {
            "url": "https://proxy.example/mcp",
            "headers": {"Authorization": "Bearer tvly-secret"},
        },
        {"url": "http://mcp.tavily.com/mcp?tavilyApiKey=tvly-secret"},
        {"url": "https://mcp.tavily.com/mcp?apiKey=tvly-secret"},
        {"url": "https://mcp.tavily.com/mcp?tavilyApiKey=not-a-tavily-key"},
        {"url": "https://not-tavily.com/mcp?tavilyApiKey=tvly-secret"},
    ],
)
def test_resolve_context_rejects_untrusted_credentials(
    monkeypatch: pytest.MonkeyPatch,
    config: dict[str, object],
) -> None:
    from src.infra.mcp.tavily_usage import resolve_tavily_context
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TAVILY_USAGE_API_KEY", "", raising=False)

    assert resolve_tavily_context("proxy", config) is None


def test_get_tavily_poll_seconds_clamps_to_provider_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.mcp.tavily_usage import get_tavily_poll_seconds
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "TAVILY_USAGE_POLL_SECONDS", 1, raising=False)

    assert get_tavily_poll_seconds() == 600
