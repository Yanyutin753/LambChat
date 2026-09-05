/** useAutoUpdate 纯函数与常量：检查节流决策。 */

import { describe, expect, test } from "vitest";

import {
  FOCUS_CHECK_MIN_INTERVAL_MS,
  PERIODIC_CHECK_INTERVAL_MS,
  shouldCheckNow,
} from "../useAutoUpdate";

describe("shouldCheckNow", () => {
  test("首次（无记录）与超间隔都应检查", () => {
    expect(shouldCheckNow(0, Date.now(), FOCUS_CHECK_MIN_INTERVAL_MS)).toBe(true);
    const hourAgo = Date.now() - FOCUS_CHECK_MIN_INTERVAL_MS - 1000;
    expect(shouldCheckNow(hourAgo, Date.now(), FOCUS_CHECK_MIN_INTERVAL_MS)).toBe(true);
  });
  test("间隔内不重复检查", () => {
    const justNow = Date.now() - 1000;
    expect(shouldCheckNow(justNow, Date.now(), FOCUS_CHECK_MIN_INTERVAL_MS)).toBe(false);
  });
  test("周期间隔常量大于聚焦间隔", () => {
    expect(PERIODIC_CHECK_INTERVAL_MS).toBeGreaterThan(FOCUS_CHECK_MIN_INTERVAL_MS);
  });
});
