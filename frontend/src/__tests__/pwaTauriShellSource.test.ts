import { readFileSync } from "node:fs";

/** 桌面壳内 PWA service worker 的接线纪律（源码结构断言）：
 *  - pwa.ts 必须：检测 Tauri 壳 → 不注册 SW → 回收历史已注册的 SW 与缓存
 *  - ChatInput 同步导入编辑器，避免编辑器内部新增动态 chunk 就绪竞态。 */

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

test("rich composer has no nested dynamic chunk that can resolve undefined", () => {
  const source = readSource("../components/chat/ChatInput.tsx");
  expect(source).toMatch(
    /import\s*\{[\s\S]*?RichChatComposer[\s\S]*?\} from "\.\/richComposer\/RichChatComposer"/,
  );
  expect(source).not.toMatch(
    /import\("\.\/richComposer\/RichChatComposer"\)/,
  );
});
