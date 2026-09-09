import { expect, test, vi } from "vitest";
import {
  CHUNK_RELOAD_COOLDOWN_MS,
  CHUNK_RELOAD_STORAGE_KEY,
  attemptChunkReload,
  buildCacheBustedUrl,
  installChunkLoadRecovery,
  isChunkLoadError,
  shouldReloadAfterChunkError,
} from "../chunkLoadRecovery";

/** 用户实报的桌面端错误：updater 更新重启后 WebView2 缓存的旧 index.html
 *  仍引用已不存在的旧 hash chunk，动态 import 404。 */
const TAURI_STALE_CHUNK_ERROR = new TypeError(
  "Failed to fetch dynamically imported module: http://tauri.localhost/assets/RichChatComposer-6TNnBJWu.js",
);

test("isChunkLoadError matches stale-chunk fetch failures across engines", () => {
  expect(isChunkLoadError(TAURI_STALE_CHUNK_ERROR)).toBe(true);
  expect(
    isChunkLoadError(new Error("Importing a module script failed")),
  ).toBe(true);
  expect(
    isChunkLoadError(new Error("error loading dynamically imported module")),
  ).toBe(true);
  expect(
    isChunkLoadError(new Error("Unable to preload CSS for http://tauri.localhost/assets/x.css")),
  ).toBe(true);
});

test("isChunkLoadError rejects unrelated and missing errors", () => {
  expect(isChunkLoadError(new ReferenceError("x is not defined"))).toBe(false);
  expect(isChunkLoadError(undefined)).toBe(false);
  expect(isChunkLoadError(null)).toBe(false);
  expect(isChunkLoadError("random string")).toBe(false);
});

test("buildCacheBustedUrl appends chunk_reload nonce keeping existing query", () => {
  expect(buildCacheBustedUrl("http://tauri.localhost/", 1234)).toBe(
    "http://tauri.localhost/?chunk_reload=1234",
  );
  const busted = buildCacheBustedUrl(
    "https://app.example.com/chat?id=7&tab=2",
    1234,
  );
  expect(busted).toContain("id=7");
  expect(busted).toContain("tab=2");
  expect(busted).toContain("chunk_reload=1234");
});

test("buildCacheBustedUrl replaces a previous nonce", () => {
  const once = buildCacheBustedUrl("http://tauri.localhost/?chunk_reload=1", 2);
  expect(once).toBe("http://tauri.localhost/?chunk_reload=2");
});

test("shouldReloadAfterChunkError allows first attempt and blocks within cooldown", () => {
  const now = 1_000_000;
  expect(shouldReloadAfterChunkError(null, now)).toBe(true);
  expect(shouldReloadAfterChunkError(now - 1_000, now)).toBe(false);
  expect(
    shouldReloadAfterChunkError(now - CHUNK_RELOAD_COOLDOWN_MS, now),
  ).toBe(true);
});

interface FakeWindow {
  addEventListener: (
    type: string,
    listener: (event: Event) => void,
  ) => void;
  sessionStorage: { getItem(k: string): string | null; setItem(k: string, v: string): void };
  location: { href: string; replace(url: string): void };
}

function createHarness(href = "http://tauri.localhost/") {
  const listeners: Record<string, Array<(event: Event) => void>> = {};
  const store = new Map<string, string>();
  const replace = vi.fn();
  const win: FakeWindow = {
    addEventListener(type, listener) {
      (listeners[type] ??= []).push(listener);
    },
    sessionStorage: {
      getItem: (k) => store.get(k) ?? null,
      setItem: (k, v) => void store.set(k, v),
    },
    location: { href, replace },
  };
  const dispatchPreloadError = (payload: unknown): boolean => {
    const event = new Event("vite:preloadError", { cancelable: true });
    Object.assign(event, { payload });
    for (const listener of listeners["vite:preloadError"] ?? []) {
      listener(event);
    }
    return event.defaultPrevented;
  };
  return { win, dispatchPreloadError, replace, store };
}

test("installChunkLoadRecovery prevents default and reloads with cache-busted url", () => {
  const { win, dispatchPreloadError, replace, store } = createHarness();
  installChunkLoadRecovery(win);

  const prevented = dispatchPreloadError(TAURI_STALE_CHUNK_ERROR);

  expect(prevented).toBe(true);
  expect(store.get(CHUNK_RELOAD_STORAGE_KEY)).toBeTruthy();
  expect(replace).toHaveBeenCalledTimes(1);
  expect(replace).toHaveBeenCalledWith(
    expect.stringContaining("chunk_reload="),
  );
});

test("installChunkLoadRecovery swallows repeat failures without reload loop", () => {
  const { win, dispatchPreloadError, replace } = createHarness();
  installChunkLoadRecovery(win);

  // Vite 的 __vitePreload 在同一页面内会先后派发 preload 失败与 import 失败
  // 两个事件，冷却期内只允许触发一次导航
  dispatchPreloadError(TAURI_STALE_CHUNK_ERROR);
  const preventedAgain = dispatchPreloadError(TAURI_STALE_CHUNK_ERROR);

  expect(preventedAgain).toBe(true);
  expect(replace).toHaveBeenCalledTimes(1);
});

test("installChunkLoadRecovery allows another reload after cooldown", () => {
  const { win, dispatchPreloadError, replace } = createHarness();
  let now = 1_000_000;
  installChunkLoadRecovery(win, { now: () => now });

  dispatchPreloadError(TAURI_STALE_CHUNK_ERROR);
  now += CHUNK_RELOAD_COOLDOWN_MS + 1;
  dispatchPreloadError(TAURI_STALE_CHUNK_ERROR);

  expect(replace).toHaveBeenCalledTimes(2);
});

test("installChunkLoadRecovery ignores non-chunk preload errors", () => {
  const { win, dispatchPreloadError, replace } = createHarness();
  installChunkLoadRecovery(win);

  const prevented = dispatchPreloadError(new Error("some random failure"));

  expect(prevented).toBe(false);
  expect(replace).not.toHaveBeenCalled();
});

test("attemptChunkReload reloads with cache-busted url respecting cooldown", () => {
  // ErrorBoundary 等非 vite:preloadError 入口共用同一自愈路径：带 bust 重载
  // 一次，冷却期内拒绝再次导航（防真坏掉时无限重载）。
  const { win, replace, store } = createHarness();
  let now = 1_000_000;

  expect(attemptChunkReload(win, { now: () => now })).toBe(true);
  expect(replace).toHaveBeenCalledTimes(1);
  expect(replace).toHaveBeenCalledWith(
    expect.stringContaining("chunk_reload="),
  );

  now += 1_000;
  expect(attemptChunkReload(win, { now: () => now })).toBe(false);
  expect(replace).toHaveBeenCalledTimes(1);
  expect(store.get(CHUNK_RELOAD_STORAGE_KEY)).toBeTruthy();

  now += CHUNK_RELOAD_COOLDOWN_MS;
  expect(attemptChunkReload(win, { now: () => now })).toBe(true);
  expect(replace).toHaveBeenCalledTimes(2);
});
