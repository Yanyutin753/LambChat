"""默认 Agent 解析：chat 路由不得硬编码 "search" 作为默认值。

未显式携带 agent_id 的请求应回落到 settings.DEFAULT_AGENT（默认 "fast"），
否则无沙箱部署下会静默落到 search agent 并触发沙箱初始化。
"""

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
    assert resolve_default_agent_id("fast") == "fast"
    assert resolve_default_agent_id("search") == "search"
    assert resolve_default_agent_id("  team  ") == "team"


def test_stream_route_does_not_hardcode_search_default():
    param = inspect.signature(chat_stream).parameters["agent_id"]
    assert param.default != "search"
