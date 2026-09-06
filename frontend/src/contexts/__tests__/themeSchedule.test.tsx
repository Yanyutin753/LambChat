/** @vitest-environment jsdom */

import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  updateMetadata: vi.fn().mockResolvedValue(undefined),
}));

vi.mock("../../services/api", () => ({
  authApi: { updateMetadata: mocks.updateMetadata },
}));

import { ThemeProvider, useTheme } from "../ThemeContext";
import type { ThemeSchedule } from "../../utils/themeDom";

const NIGHT_SCHEDULE: ThemeSchedule = {
  enabled: true,
  nightStart: "22:00",
  nightEnd: "07:00",
  nightTheme: "sepia",
};

function renderThemeHook() {
  return renderHook(() => useTheme(), {
    wrapper: ({ children }) => <ThemeProvider>{children}</ThemeProvider>,
  });
}

beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  });
});

beforeEach(() => {
  vi.useFakeTimers();
  window.localStorage.clear();
  document.documentElement.className = "";
  mocks.updateMetadata.mockClear();
  mocks.updateMetadata.mockResolvedValue(undefined);
});

afterEach(() => {
  vi.useRealTimers();
});

test("enabling a night schedule switches to the night theme immediately and persists", () => {
  vi.setSystemTime(new Date(2026, 8, 5, 23, 0));
  const { result } = renderThemeHook();
  expect(result.current.theme).toBe("light");

  act(() => result.current.setSchedule(NIGHT_SCHEDULE));

  expect(result.current.theme).toBe("sepia");
  expect(window.localStorage.getItem("lambchat-theme-schedule")).toBe(
    JSON.stringify({
      enabled: true,
      night_start: "22:00",
      night_end: "07:00",
      night_theme: "sepia",
    }),
  );
});

test("manual theme toggle exits the schedule and disables it in storage", () => {
  vi.setSystemTime(new Date(2026, 8, 5, 23, 0));
  const { result } = renderThemeHook();
  act(() => result.current.setSchedule(NIGHT_SCHEDULE));
  expect(result.current.theme).toBe("sepia");

  act(() => result.current.toggleTheme());

  expect(result.current.theme).toBe("light");
  expect(result.current.schedule?.enabled).toBe(false);
  expect(
    JSON.parse(
      window.localStorage.getItem("lambchat-theme-schedule") ?? "{}",
    ).enabled,
  ).toBe(false);
});

test("the scheduler re-evaluates the theme when the night window ends", () => {
  vi.setSystemTime(new Date(2026, 8, 5, 23, 0));
  const { result } = renderThemeHook();
  act(() => result.current.setSchedule(NIGHT_SCHEDULE));
  expect(result.current.theme).toBe("sepia");

  act(() => {
    vi.setSystemTime(new Date(2026, 8, 6, 8, 0));
    vi.advanceTimersByTime(31_000);
  });

  expect(result.current.theme).toBe("light");
});
