import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

test("main.tsx installs chunk load recovery before rendering the app", () => {
  const source = readFileSync(
    resolve(import.meta.dirname, "../main.tsx"),
    "utf8",
  );

  // 桌面端 updater 更新重启后 WebView2 可能仍用缓存的旧 index.html，
  // 引用的旧 hash chunk 已不存在 → 动态 import 失败。入口必须安装
  // vite:preloadError 恢复：吞掉错误并带 cache-bust 参数重载一次
  const installIndex = source.indexOf("installChunkLoadRecovery()");
  expect(installIndex).toBeGreaterThan(-1);
  expect(source.indexOf("createRoot(")).toBeGreaterThan(installIndex);
});
