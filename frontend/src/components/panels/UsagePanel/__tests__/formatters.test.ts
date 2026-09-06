import { describe, expect, test } from "vitest";

import { fmt, fmtCostUsd, pct, precise } from "../formatters";

describe("fmt number abbreviation", () => {
  test("keeps plain numbers below 1K", () => {
    expect(fmt(0)).toBe("0");
    expect(fmt(42)).toBe("42");
    expect(fmt(999)).toBe("999");
  });

  test("abbreviates thousands as K", () => {
    expect(fmt(1_000)).toBe("1.0K");
    expect(fmt(23_400)).toBe("23.4K");
  });

  test("abbreviates millions as M", () => {
    expect(fmt(1_000_000)).toBe("1.0M");
    expect(fmt(12_300_000)).toBe("12.3M");
  });

  test("abbreviates billions as B", () => {
    expect(fmt(1_000_000_000)).toBe("1.0B");
    expect(fmt(2_500_000_000)).toBe("2.5B");
  });

  test("abbreviates trillions as T", () => {
    expect(fmt(1_000_000_000_000)).toBe("1.0T");
    expect(fmt(7_600_000_000_000)).toBe("7.6T");
  });
});

describe("pct", () => {
  test("formats ratio as rounded percentage", () => {
    expect(pct(0.1234)).toBe("12%");
    expect(pct(0.005)).toBe("1%");
  });
});

describe("precise", () => {
  test("trims trailing zero", () => {
    expect(precise(1.04)).toBe("1");
    expect(precise(1.06)).toBe("1.1");
  });
});

describe("fmtCostUsd", () => {
  test("formats priced log cost in display currency", () => {
    expect(fmtCostUsd(0.0246, true, { language: "en" })).toBe("$0.0246");
    expect(
      fmtCostUsd(0.05, true, {
        language: "zh",
        rates: { base: "USD", rates: { CNY: 7.1 }, synced_at: null },
      }),
    ).toContain("0.355");
  });

  test("unpriced log shows dash placeholder", () => {
    expect(fmtCostUsd(0, false, { language: "en" })).toBe("—");
    expect(fmtCostUsd(undefined, false, { language: "en" })).toBe("—");
  });

  test("priced log with missing amount formats zero", () => {
    expect(fmtCostUsd(undefined, true, { language: "en" })).toBe("$0.00");
  });

  test("maxDecimals caps tiny cost precision for mobile", () => {
    expect(fmtCostUsd(0.0246, true, { language: "en", maxDecimals: 3 })).toBe(
      "$0.025",
    );
  });
});
