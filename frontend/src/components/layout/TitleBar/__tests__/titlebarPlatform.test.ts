import { expect, test } from "vitest";

import { detectDesktopOs, resolveTitlebarOs } from "../titlebarPlatform";

test("detectDesktopOs maps desktop webview user agents", () => {
  // WebView2（Windows）
  expect(
    detectDesktopOs(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    ),
  ).toBe("windows");
  // WebKitGTK（Linux）
  expect(
    detectDesktopOs(
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    ),
  ).toBe("linux");
  // WKWebView（macOS）
  expect(
    detectDesktopOs(
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    ),
  ).toBe("mac");
});

test("detectDesktopOs rejects mobile and unknown agents", () => {
  // Android WebView 含 "Linux; Android"——不能误判为 linux 桌面
  expect(
    detectDesktopOs(
      "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
    ),
  ).toBeNull();
  expect(
    detectDesktopOs("Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X)"),
  ).toBeNull();
  expect(detectDesktopOs("")).toBeNull();
});

test("resolveTitlebarOs requires the tauri runtime", () => {
  const navigator = { userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)" };
  // 无 Tauri 标记（浏览器/PWA/Capacitor）→ 永不出自绘标题栏
  expect(
    resolveTitlebarOs({
      navigator,
      __TAURI__: undefined,
      __TAURI_INTERNALS__: undefined,
    }),
  ).toBeNull();
  expect(resolveTitlebarOs({ navigator, __TAURI__: {} })).toBe("windows");
  expect(resolveTitlebarOs({ navigator, __TAURI_INTERNALS__: {} })).toBe(
    "windows",
  );
});
