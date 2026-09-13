"""MCP 根路由无尾斜杠别名回归测试。

背景：staging/nginx 的 SPA fallback 会抢答未被后端精确注册的 /api/mcp
（无斜杠）返回 index.html，导致 mcpApi.list()/create() 解析失败、MCP 面板
与角色编辑器的 MCP 绑定选择器为空。后端在根路由上同时注册 "" 与 "/"。
"""

from src.api.routes import mcp


def test_mcp_root_routes_accept_empty_path() -> None:
    paths = {
        (getattr(route, "path", None), method)
        for route in mcp.router.routes
        for method in getattr(route, "methods", set())
    }
    assert ("", "GET") in paths
    assert ("/", "GET") in paths
    assert ("", "POST") in paths
    assert ("/", "POST") in paths
