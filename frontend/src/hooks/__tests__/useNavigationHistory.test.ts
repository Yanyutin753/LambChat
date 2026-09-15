import { expect, test } from "vitest";

import {
  applyNavigation,
  canGoBack,
  canGoForward,
  createNavHistoryStack,
  resolvePopDelta,
} from "../navigationHistoryStack";

test("initial stack has no back/forward", () => {
  const stack = createNavHistoryStack("/chat");
  expect(canGoBack(stack)).toBe(false);
  expect(canGoForward(stack)).toBe(false);
});

test("push advances the cursor and enables back", () => {
  let stack = createNavHistoryStack("/chat");
  stack = applyNavigation(stack, { kind: "push", key: "/settings" });
  expect(canGoBack(stack)).toBe(true);
  expect(canGoForward(stack)).toBe(false);
  expect(stack.keys).toEqual(["/chat", "/settings"]);
  expect(stack.index).toBe(1);
});

test("pop moves the cursor without dropping future entries", () => {
  let stack = createNavHistoryStack("/chat");
  stack = applyNavigation(stack, { kind: "push", key: "/settings" });
  stack = applyNavigation(stack, { kind: "push", key: "/files" });
  stack = applyNavigation(stack, { kind: "pop", delta: -2, key: "/chat" });
  expect(stack.index).toBe(0);
  expect(canGoBack(stack)).toBe(false);
  expect(canGoForward(stack)).toBe(true);
  // 前进条目仍保留（浏览器语义），再前进 delta +2 回到 /files
  stack = applyNavigation(stack, { kind: "pop", delta: 2, key: "/files" });
  expect(stack.index).toBe(2);
  expect(canGoForward(stack)).toBe(false);
});

test("push after back truncates the forward branch", () => {
  let stack = createNavHistoryStack("/chat");
  stack = applyNavigation(stack, { kind: "push", key: "/settings" });
  stack = applyNavigation(stack, { kind: "push", key: "/files" });
  stack = applyNavigation(stack, { kind: "pop", delta: -1, key: "/settings" });
  stack = applyNavigation(stack, { kind: "push", key: "/memory" });
  expect(stack.keys).toEqual(["/chat", "/settings", "/memory"]);
  expect(stack.index).toBe(2);
  expect(canGoForward(stack)).toBe(false);
});

test("replace rewrites only the current entry", () => {
  let stack = createNavHistoryStack("/chat");
  stack = applyNavigation(stack, { kind: "push", key: "/chat/a" });
  stack = applyNavigation(stack, { kind: "push", key: "/files" });
  stack = applyNavigation(stack, { kind: "replace", key: "/bookmarks" });
  expect(stack.keys).toEqual(["/chat", "/chat/a", "/bookmarks"]);
  expect(stack.index).toBe(2);
});

test("pop clamps to stack bounds and syncs cursor key", () => {
  let stack = createNavHistoryStack("/chat");
  stack = applyNavigation(stack, { kind: "push", key: "/settings" });
  // 越界 delta 不应移出数组
  stack = applyNavigation(stack, { kind: "pop", delta: -9, key: "/chat" });
  expect(stack.index).toBe(0);
  stack = applyNavigation(stack, { kind: "pop", delta: 9, key: "/settings" });
  expect(stack.index).toBe(1);
  // delta 归零视为原地替换（key 变化时刷新当前条目）
  stack = applyNavigation(stack, { kind: "pop", delta: 0, key: "/files" });
  expect(stack.keys).toEqual(["/chat", "/files"]);
});

test("resolvePopDelta derives delta from browser history indexes", () => {
  // 正常后退：3 → 1
  expect(resolvePopDelta(3, 1)).toBe(-2);
  // 前进：0 → 1
  expect(resolvePopDelta(0, 1)).toBe(1);
  // 任一侧未知（刷新后 idx 缺失等）→ null（调用方降级为 replace）
  expect(resolvePopDelta(null, 1)).toBeNull();
  expect(resolvePopDelta(3, null)).toBeNull();
  expect(resolvePopDelta(null, null)).toBeNull();
});
