import {
  buildTodayUsageSnapshot,
  cacheHitRateFromTokens,
} from "../todayUsageSnapshot";
import type { UsageStats } from "../../../types/usage";
import type { FxRatesDoc } from "../../../utils/currency";

const rates: FxRatesDoc = { base: "USD", rates: { CNY: 7.2 } };

function stats(overrides: Partial<UsageStats> = {}): UsageStats {
  return {
    total_requests: 3,
    total_input_tokens: 100,
    total_output_tokens: 50,
    total_tokens: 150,
    total_cache_creation_tokens: 20,
    total_cache_read_tokens: 30,
    total_cost_usd: 0.5,
    total_duration: 12,
    cache_unknown_requests: 0,
    ...overrides,
  };
}

test("returns null when stats are unavailable", () => {
  expect(buildTodayUsageSnapshot(null, { language: "zh", rates })).toBeNull();
  expect(
    buildTodayUsageSnapshot(undefined, { language: "zh", rates }),
  ).toBeNull();
});

test("unknown cache observations do not become a measured hit rate", () => {
  expect(
    buildTodayUsageSnapshot(stats({ cache_unknown_requests: 1 }), {
      language: "en",
    })!.cacheHitRate,
  ).toBeNull();
});

test("an incomplete token partition cannot be displayed as measured percentages", () => {
  expect(
    buildTodayUsageSnapshot(stats({ usage_unknown_requests: 1 }), {
      language: "en",
    })!.sharesKnown,
  ).toBe(false);
  expect(
    buildTodayUsageSnapshot(stats({ usage_unknown_requests: 0 }), {
      language: "en",
    })!.sharesKnown,
  ).toBe(true);
});

test("missing cache counts are not interpreted as explicit zero", () => {
  expect(cacheHitRateFromTokens(100, undefined, 0)).toBeNull();
  expect(cacheHitRateFromTokens(100, 0, undefined)).toBe(0);
  expect(cacheHitRateFromTokens(100, 0, 0)).toBe(0);
  expect(cacheHitRateFromTokens(0, 5, 0, ["input_tokens"])).toBeNull();
});

test("explicit zero reads are zero for every positive denominator without inventing write usage", () => {
  expect(
    cacheHitRateFromTokens(633, 0, undefined, ["cache_creation_tokens"]),
  ).toBe(0);
  expect(
    cacheHitRateFromTokens(633, 0, undefined, ["cache_read_tokens"]),
  ).toBeNull();
  expect(
    cacheHitRateFromTokens(633, 0, undefined, ["input_tokens"]),
  ).toBeNull();
  expect(
    cacheHitRateFromTokens(0, 0, undefined, ["cache_creation_tokens"]),
  ).toBeNull();
});

test("certified inclusive input permits a read rate without certifying missing writes", () => {
  expect(
    cacheHitRateFromTokens(100, 80, undefined, ["cache_creation_tokens"], true),
  ).toBe(0.8);
  expect(
    cacheHitRateFromTokens(100, 0, undefined, ["cache_creation_tokens"], true),
  ).toBe(0);
  expect(
    cacheHitRateFromTokens(
      100,
      80,
      undefined,
      ["cache_creation_tokens"],
      false,
    ),
  ).toBeNull();
  expect(
    cacheHitRateFromTokens(
      100,
      undefined,
      undefined,
      ["cache_read_tokens"],
      true,
    ),
  ).toBeNull();
  expect(cacheHitRateFromTokens(0, 0, undefined, [], true)).toBeNull();
  expect(cacheHitRateFromTokens(10, 100, undefined, [], true)).toBeNull();
});

test("positive cache reads require inclusive input certification even with complete counts", () => {
  expect(cacheHitRateFromTokens(100, 80, 0)).toBeNull();
  expect(cacheHitRateFromTokens(100, 80, 0, [], false)).toBeNull();
  expect(cacheHitRateFromTokens(100, 80, 0, [], true)).toBe(0.8);
});

test("legacy aggregate counts do not certify a positive cache rate", () => {
  expect(
    buildTodayUsageSnapshot(stats({ cache_unknown_requests: undefined }), {
      language: "en",
    })!.cacheHitRate,
  ).toBeNull();
  expect(
    buildTodayUsageSnapshot(stats({ cache_unknown_requests: 0 }), {
      language: "en",
    })!.cacheHitRate,
  ).toBe(0.3);
});

test("builds amount, requests and cache hit rate from today's stats", () => {
  const snap = buildTodayUsageSnapshot(stats(), { language: "zh", rates });
  expect(snap).not.toBeNull();
  expect(snap!.amount).toBe("¥3.600");
  expect(snap!.requests).toBe(3);
  // input_tokens 已包含 cache-read，口径与后端 dashboard/单消息一致。
  expect(snap!.cacheHitRate).toBeCloseTo(30 / 100, 5);
});

test("token shares partition prompt input without double-counting cache tokens", () => {
  const snap = buildTodayUsageSnapshot(stats(), { language: "zh", rates });
  const byKey = Object.fromEntries(snap!.shares.map((s) => [s.key, s]));
  // input_tokens 已包含 cache-read/cache-write：有效 prompt 输入为 100，非缓存输入为 50。
  expect(byKey.input.share).toBeCloseTo((50 / 150) * 100, 5);
  expect(byKey.output.share).toBeCloseTo((50 / 150) * 100, 5);
  expect(byKey.cacheWrite.share).toBeCloseTo((20 / 150) * 100, 5);
  expect(byKey.cacheRead.share).toBeCloseTo((30 / 150) * 100, 5);
  const total = snap!.shares.reduce((sum, s) => sum + s.share, 0);
  expect(total).toBeCloseTo(100, 5);
});

test("uncertified provider input cannot produce a positive rate", () => {
  const snap = buildTodayUsageSnapshot(
    stats({
      total_input_tokens: 108,
      total_cache_creation_tokens: 12000,
      total_cache_read_tokens: 14813,
      cache_unknown_requests: 1,
    }),
    { language: "zh", rates },
  );

  expect(snap!.cacheHitRate).toBeNull();
  const byKey = Object.fromEntries(snap!.shares.map((s) => [s.key, s]));
  expect(byKey.input.tokens).toBe(0);
  expect(byKey.cacheRead.tokens).toBe(14813);
});

test("empty token stats yield zero shares and no cache hit rate", () => {
  const snap = buildTodayUsageSnapshot(
    stats({
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_cache_creation_tokens: 0,
      total_cache_read_tokens: 0,
    }),
    { language: "zh", rates },
  );
  expect(snap!.cacheHitRate).toBeNull();
  for (const share of snap!.shares) {
    expect(share.share).toBe(0);
  }
});

test("cacheHitRateFromTokens rejects ambiguous or inconsistent provider counts", () => {
  expect(cacheHitRateFromTokens(100, 30, 20, [], true)).toBeCloseTo(0.3, 5);
  expect(cacheHitRateFromTokens(10, 100, 50)).toBeNull();
  expect(cacheHitRateFromTokens(0, 14813, 12000)).toBeNull();
  expect(cacheHitRateFromTokens(10, 100, 0, [], true)).toBeNull();
  // 无任何 token → null（调用方隐藏该指标）
  expect(cacheHitRateFromTokens(0, 0, 0)).toBeNull();
});
