import { expect, test } from "vitest";

/**
 * 纯逻辑契约测试：windowControls service 的公开面。
 * Tauri API 细节由组件测试通过 mock 本模块覆盖；这里锁定
 * 模块导出形状（组件依赖的调用面），防止意外破坏。
 */

import * as windowControls from "../windowControls";

test("exports the window control surface used by the titlebar", () => {
  expect(typeof windowControls.minimizeWindow).toBe("function");
  expect(typeof windowControls.toggleMaximizeWindow).toBe("function");
  expect(typeof windowControls.closeWindow).toBe("function");
  expect(typeof windowControls.queryWindowMaximized).toBe("function");
  expect(typeof windowControls.subscribeWindowResized).toBe("function");
});
