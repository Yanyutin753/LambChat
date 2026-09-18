"""自定义中间件应使用纯 ASGI 实现而非 BaseHTTPMiddleware。

BaseHTTPMiddleware 每层每请求创建 task 并拷贝 request/response 流，
4 层栈的吞吐税显著；纯 ASGI 包装零额外开销。
"""

from __future__ import annotations

from pathlib import Path

SRC = Path("src/api/middleware")

PUBLIC_CLASSES = {
    "tracing.py": "TracingMiddleware",
    "auth.py": "AuthMiddleware",
    "user_context.py": "UserContextMiddleware",
}


def test_custom_middlewares_are_pure_asgi() -> None:
    for filename, cls in PUBLIC_CLASSES.items():
        source = (SRC / filename).read_text(encoding="utf-8")
        assert "BaseHTTPMiddleware" not in source, f"{filename} 仍继承 BaseHTTPMiddleware"
        assert f"class {cls}:" in source, f"{filename} 缺少 {cls} 类定义"
        assert "async def __call__(self, scope" in source, f"{filename} 缺少 ASGI __call__"
        # 非 http scope（websocket/lifespan）必须原样透传
        assert 'scope["type"] != "http"' in source, f"{filename} 未透传非 http scope"
