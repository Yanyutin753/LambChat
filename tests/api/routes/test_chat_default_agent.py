"""Configured agent defaults and legacy Fast Agent compatibility."""

from __future__ import annotations

import inspect

from src.api.routes.chat import chat_stream, resolve_default_agent_id
from src.kernel.config import settings


def test_missing_agent_id_falls_back_to_default_agent():
    assert resolve_default_agent_id(None) == settings.DEFAULT_AGENT


def test_blank_agent_id_falls_back_to_default_agent():
    assert resolve_default_agent_id("") == settings.DEFAULT_AGENT
    assert resolve_default_agent_id("   ") == settings.DEFAULT_AGENT


def test_explicit_agent_id_is_preserved():
    assert resolve_default_agent_id("fast") == "search"
    assert resolve_default_agent_id("search") == "search"
    assert resolve_default_agent_id("  team  ") == "team"


def test_stream_route_does_not_hardcode_search_default():
    param = inspect.signature(chat_stream).parameters["agent_id"]
    assert param.default != "search"


def test_legacy_default_agent_is_normalized(monkeypatch):
    monkeypatch.setattr(settings, "DEFAULT_AGENT", "fast")
    assert resolve_default_agent_id(None) == "search"
