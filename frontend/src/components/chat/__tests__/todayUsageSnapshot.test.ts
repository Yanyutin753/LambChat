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
    ...overrides,
  };
}

test("returns null when stats are unavailable", () => {
  expect(buildTodayUsageSnapshot(null, { language: "zh", rates })).toBeNull();
  expect(
    buildTodayUsageSnapshot(undefined, { language: "zh", rates }),
  ).toBeNull();
});

test("builds amount, requests and cache hit rate from today's stats", () => {
  const snap = buildTodayUsageSnapshot(stats(), { language: "zh", rates });
  expect(snap).not.toBeNull();
  expect(snap!.amount).toBe("¥3.60");
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

test("cache metrics remain bounded when provider input excludes cached tokens", () => {
  const snap = buildTodayUsageSnapshot(
    stats({
      total_input_tokens: 108,
      total_cache_creation_tokens: 12000,
      total_cache_read_tokens: 14813,
    }),
    { language: "zh", rates },
  );

  expect(snap!.cacheHitRate).toBeCloseTo(14813 / 26813, 5);
  expect(snap!.cacheHitRate).toBeLessThanOrEqual(1);
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

test("cacheHitRateFromTokens normalizes provider token semantics", () => {
  // 标准口径：input 已含缓存 → 分母即 input
  expect(cacheHitRateFromTokens(100, 30, 20)).toBeCloseTo(0.3, 5);
  // provider input 不含缓存：分母取 max(input, read+write)
  expect(cacheHitRateFromTokens(10, 100, 50)).toBeCloseTo(100 / 150, 5);
  expect(cacheHitRateFromTokens(0, 14813, 12000)).toBeCloseTo(14813 / 26813, 5);
  // cache 超过 input 时 clamp 到 1，不允许出现 1000%
  expect(cacheHitRateFromTokens(10, 100, 0)).toBe(1);
  // 无任何 token → null（调用方隐藏该指标）
  expect(cacheHitRateFromTokens(0, 0, 0)).toBeNull();
});
