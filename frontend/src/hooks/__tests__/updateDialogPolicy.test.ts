import { expect, test } from "vitest";

import { shouldOpenUpdateDialog } from "../useAutoUpdate";

test("update modal is reserved for mobile platforms", () => {
  // 桌面端（tauri）：完全后台 + 标题栏指示器，永不弹阻塞式对话框
  expect(shouldOpenUpdateDialog("tauri")).toBe(false);
  // 移动端：安装本身需要用户确认（APK intent / App Store），保留对话框
  expect(shouldOpenUpdateDialog("android")).toBe(true);
  expect(shouldOpenUpdateDialog("ios")).toBe(true);
});
