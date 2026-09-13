from __future__ import annotations

"""enabled_mcp_servers（persona MCP 白名单）链路穿透验证。

对齐 test_disabled_skills_config_propagation 的验证思路：断言
请求字段 → chat 路由 → agent graph kwargs → context → 运行时过滤
各环节都存在，防止后续重构悄悄断链。
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_agent_request_has_enabled_mcp_servers_field() -> None:
    src = _read("src/kernel/schemas/agent.py")
    assert "enabled_mcp_servers: Optional[list[str]]" in src


def test_chat_routes_thread_enabled_mcp_servers() -> None:
    src = _read("src/api/routes/chat.py")
    assert "enabled_mcp_servers: list[str] | None = None" in src
    assert src.count("enabled_mcp_servers=request.enabled_mcp_servers") >= 2
    assert "enabled_mcp_servers=enabled_mcp_servers" in src


def test_persona_request_config_sets_whitelist_from_snapshot() -> None:
    src = _read("src/api/routes/chat_request_config.py")
    assert "_persona_enabled_mcp_servers_from_snapshot" in src
    assert (
        "request.enabled_mcp_servers = _persona_enabled_mcp_servers_from_snapshot(snapshot)" in src
    )
    assert '"enabled_mcp_servers": request.enabled_mcp_servers' in src


def test_agent_graphs_pass_whitelist_into_contexts() -> None:
    for rel in (
        "src/agents/fast_agent/graph.py",
        "src/agents/search_agent/graph.py",
        "src/agents/team_agent/graph.py",
    ):
        src = _read(rel)
        assert 'kwargs.get("enabled_mcp_servers")' in src, rel
        assert "enabled_mcp_servers=enabled_mcp_servers" in src, rel


def test_contexts_filter_mcp_tools_by_whitelist() -> None:
    for rel in (
        "src/agents/fast_agent/context.py",
        "src/agents/search_agent/context.py",
    ):
        src = _read(rel)
        assert "enabled_mcp_servers" in src, rel
        assert "filter_mcp_tools_by_server_whitelist" in src, rel
