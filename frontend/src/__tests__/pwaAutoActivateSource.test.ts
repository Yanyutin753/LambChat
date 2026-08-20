import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "vitest";

test("pwa.ts activates a waiting worker at page load", () => {
  const source = readFileSync(
    resolve(import.meta.dirname, "../pwa.ts"),
    "utf8",
  );

  // 页面加载时若存在 waiting 的新版本 worker，直接激活并重载一次，
  // 避免用户浏览器长期停留在旧缓存 bundle（旧版本的性能/行为修复不生效）
  expect(source).toMatch(
    /activateWaitingLambChatPwaUpdate\(registration\)/,
  );
  // 仅在存在旧 controller（即确实在跑旧版本）且成功触发激活时重载
  expect(source).toMatch(
    /navigator\.serviceWorker\.controller\s*&&\s*registration\.waiting/,
  );
});
