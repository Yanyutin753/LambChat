import { readFileSync } from "node:fs";

/** 桌面壳内 PWA service worker 的接线纪律（源码结构断言）：
 *  - pwa.ts 必须：检测 Tauri 壳 → 不注册 SW → 回收历史已注册的 SW 与缓存
 *  - ChatInput 的 lazy 工厂必须在 module 为 undefined 时抛回 chunk 错误形态
 *    （vite:preloadError 被吞掉后动态 import resolve 成 undefined） */

function readSource(relativePath: string): string {
  const url = new URL(relativePath, import.meta.url);
  return readFileSync(url, "utf8");
}

test("registerLambChatPwa skips registration and cleans up inside the Tauri shell", () => {
  const source = readSource("../pwa.ts");
  expect(source).toMatch(/isTauriShell/);
  expect(source).toMatch(/shouldRegisterPwa\(\{[\s\S]*?isTauriShell/);
  // 壳内回收：unregister 历史注册 + 清 Cache Storage
  expect(source).toMatch(/getRegistrations/);
  expect(source).toMatch(/unregister/);
  expect(source).toMatch(/caches\.keys/);
});

test("rich composer lazy factory surfaces undefined module as a chunk error", () => {
  const source = readSource("../components/chat/ChatInput.tsx");
  expect(source).toMatch(
    /if \(!module\)[\s\S]*?Failed to fetch dynamically imported module/,
  );
});
