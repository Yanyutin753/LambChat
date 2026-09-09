/** useAutoUpdate 纯函数与常量：检查节流决策。 */

import { describe, expect, test } from "vitest";

import {
  FOCUS_CHECK_MIN_INTERVAL_MS,
  PERIODIC_CHECK_INTERVAL_MS,
  isLinuxDesktopEnvironment,
  shouldCheckNow,
} from "../useAutoUpdate";

describe("shouldCheckNow", () => {
  test("首次（无记录）与超间隔都应检查", () => {
    expect(shouldCheckNow(0, Date.now(), FOCUS_CHECK_MIN_INTERVAL_MS)).toBe(
      true,
    );
    const hourAgo = Date.now() - FOCUS_CHECK_MIN_INTERVAL_MS - 1000;
    expect(
      shouldCheckNow(hourAgo, Date.now(), FOCUS_CHECK_MIN_INTERVAL_MS),
    ).toBe(true);
  });
  test("间隔内不重复检查", () => {
    const justNow = Date.now() - 1000;
    expect(
      shouldCheckNow(justNow, Date.now(), FOCUS_CHECK_MIN_INTERVAL_MS),
    ).toBe(false);
  });
  test("周期间隔常量大于聚焦间隔", () => {
    expect(PERIODIC_CHECK_INTERVAL_MS).toBeGreaterThan(
      FOCUS_CHECK_MIN_INTERVAL_MS,
    );
  });
});

describe("isLinuxDesktopEnvironment", () => {
  test("Linux UA 或 platform 命中即 Linux 桌面", () => {
    expect(
      isLinuxDesktopEnvironment({
        userAgent: "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        platform: "Linux x86_64",
      }),
    ).toBe(true);
    expect(isLinuxDesktopEnvironment({ platform: "Linux aarch64" })).toBe(true);
  });
  test("mac/Windows/移动端不算 Linux 桌面", () => {
    expect(
      isLinuxDesktopEnvironment({
        userAgent:
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15",
        platform: "MacIntel",
      }),
    ).toBe(false);
    expect(
      isLinuxDesktopEnvironment({
        userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        platform: "Win32",
      }),
    ).toBe(false);
    // Android WebView UA 含 "Linux; Android"——不是桌面 Linux
    expect(
      isLinuxDesktopEnvironment({
        userAgent: "Mozilla/5.0 (Linux; Android 14; Pixel 8)",
        platform: "",
      }),
    ).toBe(false);
  });
});
