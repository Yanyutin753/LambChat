/** @vitest-environment jsdom */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { THEME_SCHEDULE_CHANGE_EVENT, THEME_SCHEDULE_KEY } from "../../utils/themeDom";

vi.mock("../../services/api", () => ({
  authApi: { updateMetadata: vi.fn().mockResolvedValue({}) },
}));

import { ThemeProvider, useTheme } from "../ThemeContext";

function seedSchedule(schedule: unknown) {
  localStorage.setItem(THEME_SCHEDULE_KEY, JSON.stringify(schedule));
}

function stubMatchMedia() {
  window.matchMedia = vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  stubMatchMedia();
  localStorage.removeItem(THEME_SCHEDULE_KEY);
  localStorage.removeItem("lambchat-theme");
});

afterEach(() => {
  vi.useRealTimers();
});

test("applies the scheduled night theme while inside the night window", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 8, 12, 22, 30));
  seedSchedule({ enabled: true, start: "22:00", end: "07:00", nightTheme: "sepia" });

  const { result } = renderHook(() => useTheme(), { wrapper: ThemeProvider });

  expect(result.current.theme).toBe("sepia");
});

test("stays on light outside the night window", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 8, 12, 12, 0));
  seedSchedule({ enabled: true, start: "22:00", end: "07:00", nightTheme: "dark" });

  const { result } = renderHook(() => useTheme(), { wrapper: ThemeProvider });

  expect(result.current.theme).toBe("light");
});

test("manual switch exits auto mode and stops future flips", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 8, 12, 22, 30));
  seedSchedule({ enabled: true, start: "22:00", end: "23:59", nightTheme: "sepia" });

  const { result } = renderHook(() => useTheme(), { wrapper: ThemeProvider });
  expect(result.current.theme).toBe("sepia");

  act(() => {
    result.current.setTheme("light");
  });
  expect(result.current.theme).toBe("light");
  expect(JSON.parse(localStorage.getItem(THEME_SCHEDULE_KEY)!).enabled).toBe(false);

  // 夜窗仍未结束：自动模式已被手动切换退出，主题不再被翻转
  act(() => {
    vi.advanceTimersByTime(2 * 60 * 1000);
  });
  expect(result.current.theme).toBe("light");
});

test("adopts a schedule delivered through the external-change event", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date(2026, 8, 12, 23, 0));

  const { result } = renderHook(() => useTheme(), { wrapper: ThemeProvider });
  expect(result.current.theme).toBe("light");

  act(() => {
    window.dispatchEvent(
      new CustomEvent(THEME_SCHEDULE_CHANGE_EVENT, {
        detail: { enabled: true, start: "22:00", end: "07:00", nightTheme: "sepia" },
      }),
    );
  });

  expect(result.current.theme).toBe("sepia");
});
