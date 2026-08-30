import { buildTodayUsageSnapshot } from "../todayUsageSnapshot";
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
  // 缓存命中率 = 缓存读取 / (缓存读取 + 输入)
  expect(snap!.cacheHitRate).toBeCloseTo(30 / 130, 5);
});

test("token shares cover the four kinds and sum to 100", () => {
  const snap = buildTodayUsageSnapshot(stats(), { language: "zh", rates });
  const byKey = Object.fromEntries(snap!.shares.map((s) => [s.key, s]));
  // 分母 = 输入+输出+缓存写入+缓存读取 = 100+50+20+30 = 200
  expect(byKey.input.share).toBe(50);
  expect(byKey.output.share).toBe(25);
  expect(byKey.cacheWrite.share).toBe(10);
  expect(byKey.cacheRead.share).toBe(15);
  const total = snap!.shares.reduce((sum, s) => sum + s.share, 0);
  expect(total).toBeCloseTo(100, 5);
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
