"""HTTP 路由注册冒烟测试。

背景（2026-08-27 评审事故）：把 helper 函数插到 `@router.post` 装饰器与
`chat_stream` 之间，装饰器就绑定到了 helper 上，主聊天端点直接失效（422），
而所有函数级测试照常通过。函数级测试无法发现路由注册回归——这里直接断言
路由表绑定，防止同类事故复发。
"""

from __future__ import annotations

from src.api.routes.chat import chat_stream, router


def test_stream_route_binds_to_chat_stream() -> None:
    matches = [r for r in router.routes if getattr(r, "path", "") == "/stream"]
    assert matches, "POST /stream 路由丢失"
    route = matches[0]
    assert route.endpoint is chat_stream, (
        f"/stream 路由绑定到了 {route.endpoint.__name__}——"
        "检查是否有 helper 被插进了装饰器和 chat_stream 之间"
    )
    assert "POST" in route.methods
