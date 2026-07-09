import { getPwaRequestKind, isBackendPath } from "../pwaRouting.ts";

const ORIGIN = "https://lambchat.com";

test("bypasses backend, streaming, non-GET, and cross-origin requests", () => {
  expect(isBackendPath("/api/chat")).toBe(true);
  expect(isBackendPath("/ws/session")).toBe(true);
  expect(isBackendPath("/default/stream")).toBe(true);
  expect(isBackendPath("/tools/rebuild")).toBe(true);
  expect(isBackendPath("/human/approval")).toBe(true);
  expect(isBackendPath("/services/github")).toBe(true);
  expect(isBackendPath("/health")).toBe(true);

  expect(
    getPwaRequestKind({
      method: "POST",
      mode: "cors",
      url: `${ORIGIN}/chat`,
      scopeOrigin: ORIGIN,
      accept: "text/html",
    }),
  ).toBe("bypass");
  expect(
    getPwaRequestKind({
      method: "GET",
      mode: "cors",
      url: `${ORIGIN}/api/chat`,
      scopeOrigin: ORIGIN,
      accept: "application/json",
    }),
  ).toBe("bypass");
  expect(
    getPwaRequestKind({
      method: "GET",
      mode: "cors",
      url: `${ORIGIN}/tools/rebuild`,
      scopeOrigin: ORIGIN,
      accept: "application/json",
    }),
  ).toBe("bypass");
  expect(
    getPwaRequestKind({
      method: "GET",
      mode: "cors",
      url: `${ORIGIN}/chat/stream`,
      scopeOrigin: ORIGIN,
      accept: "text/event-stream",
    }),
  ).toBe("bypass");
  expect(
    getPwaRequestKind({
      method: "GET",
      mode: "cors",
      url: "https://fonts.gstatic.com/font.woff2",
      scopeOrigin: ORIGIN,
      accept: "font/woff2",
    }),
  ).toBe("bypass");
});

test("classifies SPA navigations and static assets for offline handling", () => {
  expect(
    getPwaRequestKind({
      method: "GET",
      mode: "navigate",
      url: `${ORIGIN}/chat/session-id`,
      scopeOrigin: ORIGIN,
      accept: "text/html",
    }),
  ).toBe("navigation");
  expect(
    getPwaRequestKind({
      method: "GET",
      mode: "cors",
      url: `${ORIGIN}/assets/index.abc123.js?v=1`,
      scopeOrigin: ORIGIN,
      accept: "text/javascript",
    }),
  ).toBe("static-asset");
  expect(
    getPwaRequestKind({
      method: "GET",
      mode: "cors",
      url: `${ORIGIN}/icons/icon.svg`,
      scopeOrigin: ORIGIN,
      accept: "image/svg+xml",
    }),
  ).toBe("static-asset");
});
