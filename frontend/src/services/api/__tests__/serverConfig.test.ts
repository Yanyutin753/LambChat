/** 服务器运行时配置（打包壳 base_url）：存储/归一化/网络改写。 */
/** @vitest-environment jsdom */

import { beforeEach, describe, expect, test, vi } from "vitest";

import {
  buildAbsoluteUrl,
  clearStoredServerUrl,
  effectiveApiBase,
  getStoredServerUrl,
  installServerUrlNetworkPatch,
  needsServerSetup,
  normalizeServerUrl,
  setStoredServerUrl,
} from "../serverConfig";

beforeEach(() => {
  window.localStorage.clear();
});

describe("normalizeServerUrl", () => {
  test("trims and strips trailing slashes", () => {
    expect(normalizeServerUrl(" https://lc.example.com/ ")).toBe("https://lc.example.com");
  });
  test("bare domain gets https scheme", () => {
    expect(normalizeServerUrl("lc.example.com")).toBe("https://lc.example.com");
  });
  test("localhost without dot allowed", () => {
    expect(normalizeServerUrl("http://localhost:8000")).toBe("http://localhost:8000");
  });
  test("ip allowed", () => {
    expect(normalizeServerUrl("http://192.168.1.5:8000")).toBe("http://192.168.1.5:8000");
  });
  test("empty and garbage rejected", () => {
    expect(normalizeServerUrl("  ")).toBe("");
    expect(normalizeServerUrl("not a url !")).toBe("");
  });
});

describe("storage", () => {
  test("set/get/clear roundtrip", () => {
    expect(getStoredServerUrl()).toBeNull();
    expect(setStoredServerUrl("lc.example.com")).toBe("https://lc.example.com");
    expect(getStoredServerUrl()).toBe("https://lc.example.com");
    clearStoredServerUrl();
    expect(getStoredServerUrl()).toBeNull();
  });
});

describe("effectiveApiBase / needsServerSetup", () => {
  test("stored value wins; falls back to build-time base", () => {
    setStoredServerUrl("https://runtime.example.com");
    expect(effectiveApiBase()).toBe("https://runtime.example.com");
    clearStoredServerUrl();
    expect(effectiveApiBase()).toBe("");
  });
  test("needs setup only in tauri runtime without any base", () => {
    const tauriGlobal = { __TAURI__: {} } as const;
    expect(needsServerSetup(tauriGlobal)).toBe(true);
    setStoredServerUrl("https://s.example.com");
    expect(needsServerSetup(tauriGlobal)).toBe(false);
    clearStoredServerUrl();
    expect(needsServerSetup({})).toBe(false);
  });
});

describe("installServerUrlNetworkPatch", () => {
  test("rewrites relative /api and /ws, leaves static and absolute untouched", async () => {
    const calls: string[] = [];
    const fakeFetch = vi.fn(async (input: unknown) => {
      calls.push(String(input));
      return new Response("{}");
    });
    class FakeWS {
      url: string;
      constructor(url: string | URL) {
        this.url = url.toString();
        calls.push(`ws:${this.url}`);
      }
    }

    const installed = installServerUrlNetworkPatch({
      base: "https://server.example.com",
      fetchImpl: fakeFetch as unknown as typeof fetch,
      WebSocketCtor: FakeWS as unknown as typeof WebSocket,
    });
    expect(installed).toBe(true);

    await window.fetch("/api/auth/me");
    await window.fetch("/icons/icon.svg");
    await window.fetch("https://elsewhere.example.com/api/x");
    void new window.WebSocket("/ws/notifications");

    expect(calls).toEqual([
      "https://server.example.com/api/auth/me",
      "/icons/icon.svg",
      "https://elsewhere.example.com/api/x",
      "ws:https://server.example.com/ws/notifications",
    ]);
  });

  test("no base → not installed", () => {
    expect(installServerUrlNetworkPatch({ base: "" })).toBe(false);
  });

  test("Request objects are rewritten preserving method/body", async () => {
    const seen: Array<{ url: string; method: string }> = [];
    const fakeFetch = vi.fn(async (input: unknown) => {
      const req = input as Request;
      seen.push({ url: req.url, method: req.method });
      return new Response("{}");
    });
    installServerUrlNetworkPatch({
      base: "https://s.example.com",
      fetchImpl: fakeFetch as unknown as typeof fetch,
      WebSocketCtor: class {} as unknown as typeof WebSocket,
    });
    const sameOrigin = new URL("/api/chat", window.location.href).toString();
    await window.fetch(new Request(sameOrigin, { method: "POST", body: "hi" }));
    expect(seen[0]).toEqual({ url: "https://s.example.com/api/chat", method: "POST" });
  });

  test("buildAbsoluteUrl joins base and path", () => {
    expect(buildAbsoluteUrl("/api/x", "https://s.example.com")).toBe(
      "https://s.example.com/api/x",
    );
  });
});

describe("移动端（Capacitor）运行时配置", () => {
  test("capacitor runtime needs setup when unconfigured", () => {
    const capGlobal = { Capacitor: { isNativePlatform: () => true, getPlatform: () => "android" } };
    expect(needsServerSetup(capGlobal as never)).toBe(true);
    setStoredServerUrl("https://s.example.com");
    expect(needsServerSetup(capGlobal as never)).toBe(false);
    clearStoredServerUrl();
  });
});
