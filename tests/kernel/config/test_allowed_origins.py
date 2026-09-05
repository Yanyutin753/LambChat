"""原生壳 WebView origin 与 CORS 白名单对齐（Capacitor/Tauri 各版本默认 scheme）。

背景（2026-09 Android 登录 Failed to fetch 排查）：Capacitor 5+ 的 Android
默认 ``androidScheme: "https"``，WebView origin 是 ``https://localhost``；
白名单里只有 ``http://localhost`` / ``capacitor://localhost``，导致预检 400、
无 allow-origin 头，移动端所有 API 请求被浏览器 CORS 拦截。iOS 默认
``capacitor://`` 不受影响。
"""

from src.kernel.config.base import Settings


def test_allowed_origins_defaults_cover_native_webview_origins() -> None:
    origins = Settings.model_fields["ALLOWED_ORIGINS"].default_factory()  # type: ignore[no-any-return]
    # Capacitor 6 Android（https scheme）
    assert "https://localhost" in origins
    # Capacitor 3-4 / iOS（capacitor scheme）与旧 Android（http scheme）
    assert "capacitor://localhost" in origins
    assert "http://localhost" in origins
    # Tauri 桌面壳
    assert "tauri://localhost" in origins
    assert "https://tauri.localhost" in origins
