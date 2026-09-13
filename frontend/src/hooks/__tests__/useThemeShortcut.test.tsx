/** @vitest-environment jsdom */

import { renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import { useThemeShortcut } from "../useThemeShortcut";

function keydown(init: Partial<KeyboardEvent>): KeyboardEvent {
  return new KeyboardEvent("keydown", {
    key: "l",
    bubbles: true,
    ...init,
  });
}

test("cycles the theme on Ctrl+Shift+L", () => {
  const onCycle = vi.fn();
  renderHook(() => useThemeShortcut(onCycle));

  window.dispatchEvent(keydown({ ctrlKey: true, shiftKey: true }));
  expect(onCycle).toHaveBeenCalledTimes(1);
});

test("does not cycle when focus is in an editable target", () => {
  const onCycle = vi.fn();
  renderHook(() => useThemeShortcut(onCycle));

  const input = document.createElement("input");
  document.body.appendChild(input);
  input.focus();
  input.dispatchEvent(keydown({ ctrlKey: true, shiftKey: true }));
  expect(onCycle).not.toHaveBeenCalled();

  input.remove();
});

test("does not cycle for unrelated key combos and lets them pass through", () => {
  const onCycle = vi.fn();
  renderHook(() => useThemeShortcut(onCycle));

  const plain = new KeyboardEvent("keydown", { key: "l", bubbles: true });
  const passed = window.dispatchEvent(plain);
  expect(onCycle).not.toHaveBeenCalled();
  expect(passed).toBe(true);
});

test("prevents default only when handling the shortcut", () => {
  const onCycle = vi.fn();
  renderHook(() => useThemeShortcut(onCycle));

  const handled = new KeyboardEvent("keydown", {
    key: "L",
    ctrlKey: true,
    metaKey: true,
    shiftKey: true,
    cancelable: true,
    bubbles: true,
  });
  window.dispatchEvent(handled);
  expect(handled.defaultPrevented).toBe(true);
  expect(onCycle).toHaveBeenCalledTimes(1);
});
