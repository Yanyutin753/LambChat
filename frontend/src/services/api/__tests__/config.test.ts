import {
  buildApiUrl,
  buildUploadProxyUrl,
  buildUploadProxyUrlFromKey,
  buildWebSocketUrl,
  getFullUrl,
  isNativeAppRuntime,
} from "../config.ts";

test("buildApiUrl keeps same-origin deployments relative", () => {
  expect(buildApiUrl("/api/health", "")).toBe("/api/health");
});

test("buildApiUrl prefixes relative backend paths for packaged apps", () => {
  expect(buildApiUrl("/api/health", "https://chat.example.com/")).toBe(
    "https://chat.example.com/api/health",
  );
});

test("getFullUrl prefers the configured backend for relative file URLs", () => {
  expect(
    getFullUrl("/api/upload/file/report.pdf", "https://chat.example.com"),
  ).toBe("https://chat.example.com/api/upload/file/report.pdf");
});

test("buildUploadProxyUrl leaves upload proxy URLs unchanged on web", () => {
  expect(
    buildUploadProxyUrl(
      "/api/upload/file/revealed_files/report.pdf",
      "https://chat.example.com",
    ),
  ).toBe("https://chat.example.com/api/upload/file/revealed_files/report.pdf");
});

test("buildUploadProxyUrl appends proxy mode to upload proxy URLs in native apps", () => {
  expect(
    buildUploadProxyUrl(
      "/api/upload/file/revealed_files/report.pdf",
      "https://chat.example.com",
      { locationLike: { protocol: "capacitor:" } },
    ),
  ).toBe(
    "https://chat.example.com/api/upload/file/revealed_files/report.pdf?proxy=true",
  );
});

test("buildUploadProxyUrl preserves existing query params in native apps", () => {
  expect(
    buildUploadProxyUrl(
      "https://chat.example.com/api/upload/file/revealed_files/report.pdf?download=0",
      "",
      { locationLike: { protocol: "tauri:" } },
    ),
  ).toBe(
    "https://chat.example.com/api/upload/file/revealed_files/report.pdf?download=0&proxy=true",
  );
});

test("buildUploadProxyUrl leaves non-upload URLs unchanged", () => {
  expect(
    buildUploadProxyUrl(
      "https://oss.example.com/revealed_files/report.pdf",
      "",
      {
        locationLike: { protocol: "capacitor:" },
      },
    ),
  ).toBe("https://oss.example.com/revealed_files/report.pdf");
});

test("buildUploadProxyUrlFromKey keeps native app image URLs web-compatible by default", () => {
  expect(
    buildUploadProxyUrlFromKey(
      "revealed files/report 1.pdf",
      "https://chat.example.com",
      {
        locationLike: { protocol: "capacitor:" },
      },
    ),
  ).toBe(
    "https://chat.example.com/api/upload/file/revealed%20files/report%201.pdf",
  );
});

test("buildUploadProxyUrlFromKey can force proxy mode for native content fetches", () => {
  expect(
    buildUploadProxyUrlFromKey(
      "revealed files/report 1.pdf",
      "https://chat.example.com",
      {
        force: true,
        locationLike: { protocol: "https:" },
      },
    ),
  ).toBe(
    "https://chat.example.com/api/upload/file/revealed%20files/report%201.pdf?proxy=true",
  );
});

test("isNativeAppRuntime detects native webview origins and bridges", () => {
  expect(isNativeAppRuntime({ protocol: "capacitor:" })).toBe(true);
  expect(isNativeAppRuntime({ protocol: "https:" })).toBe(false);
  expect(
    isNativeAppRuntime(
      { protocol: "https:" },
      { Capacitor: { isNativePlatform: () => true } },
    ),
  ).toBe(true);
});

test("buildWebSocketUrl points packaged apps at the configured backend", () => {
  expect(buildWebSocketUrl("/ws", "https://chat.example.com")).toBe(
    "wss://chat.example.com/ws",
  );
});

test("buildWebSocketUrl keeps same-origin browser deployments on window host", () => {
  expect(
    buildWebSocketUrl("/ws", "", {
      protocol: "http:",
      host: "localhost:3001",
    }),
  ).toBe("ws://localhost:3001/ws");
});
