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

test("available cache totals produce a rate despite incomplete observations", () => {
  expect(
    buildTodayUsageSnapshot(stats({ cache_unknown_requests: 1 }), {
      language: "en",
    })!.cacheHitRate,
  ).toBe(0.3);
});

test("available totals produce shares despite incomplete observation flags", () => {
  expect(
    buildTodayUsageSnapshot(stats({ usage_unknown_requests: 1 }), {
      language: "en",
    })!.sharesKnown,
  ).toBe(true);
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

test("legacy aggregate counts still produce a rate from reported totals", () => {
  expect(
    buildTodayUsageSnapshot(stats({ cache_unknown_requests: undefined }), {
      language: "en",
    })!.cacheHitRate,
  ).toBe(0.3);
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

test("provider input excluding cache uses the larger prompt total", () => {
  const snap = buildTodayUsageSnapshot(
    stats({
      total_input_tokens: 108,
      total_cache_creation_tokens: 12000,
      total_cache_read_tokens: 14813,
      cache_unknown_requests: 1,
    }),
    { language: "zh", rates },
  );

  expect(snap!.cacheHitRate).toBeCloseTo(14813 / 26813);
  const byKey = Object.fromEntries(snap!.shares.map((s) => [s.key, s]));
  expect(byKey.input.tokens).toBe(0);
  expect(byKey.input.reported).toBe(false);
  expect(snap!.sharesKnown).toBe(true);
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

test("56 requests use reported totals when cache writes are missing", () => {
  const snap = buildTodayUsageSnapshot(
    stats({
      total_requests: 56,
      total_input_tokens: 100,
      total_output_tokens: 50,
      total_cache_read_tokens: 30,
      total_cache_creation_tokens: 0,
      usage_unknown_requests: 56,
      cache_unknown_requests: 56,
      unknown_usage_fields: ["cache_creation_tokens"],
    }),
    { language: "en" },
  )!;
  const byKey = Object.fromEntries(snap.shares.map((row) => [row.key, row]));
  expect(byKey.input.tokens).toBe(70);
  expect(byKey.input.reported).toBe(false);
  expect(byKey.output.tokens).toBe(50);
  expect(byKey.cacheRead.tokens).toBe(30);
  expect(byKey.cacheWrite.tokens).toBe(0);
  expect(snap.sharesKnown).toBe(true);
  expect(snap.cacheHitRate).toBe(0.3);
});

test("invalid counters are skipped while reported zeros stay visible", () => {
  const snap = buildTodayUsageSnapshot(
    stats({
      total_input_tokens: Number.NaN,
      total_output_tokens: 0,
      total_cache_read_tokens: 0,
      total_cache_creation_tokens: -1,
      usage_unknown_requests: 1,
      cache_unknown_requests: 1,
      unknown_usage_fields: ["input_tokens", "cache_creation_tokens"],
    }),
    { language: "en" },
  )!;
  const byKey = Object.fromEntries(snap.shares.map((row) => [row.key, row]));
  expect(byKey.input.tokens).toBe(0);
  expect(byKey.output.tokens).toBe(0);
  expect(byKey.cacheRead.tokens).toBe(0);
  expect(byKey.cacheWrite.tokens).toBeNull();
  expect(snap.sharesKnown).toBe(true);
});

test("legacy valid counters produce a token partition", () => {
  const snap = buildTodayUsageSnapshot(
    stats({ cache_unknown_requests: undefined }),
    { language: "en" },
  )!;
  expect(snap.sharesKnown).toBe(true);
  expect(snap.shares.find((row) => row.key === "input")?.tokens).toBe(50);
  expect(snap.shares.find((row) => row.key === "input")?.reported).toBe(false);
  expect(snap.shares.find((row) => row.key === "output")?.tokens).toBe(50);
});

test("one incomplete request does not hide the day's reported totals", () => {
  const snap = buildTodayUsageSnapshot(
    stats({
      total_requests: 60,
      total_input_tokens: 11285204,
      total_output_tokens: 529631,
      total_cache_read_tokens: 9121344,
      total_cache_creation_tokens: 0,
      usage_unknown_requests: 60,
      cache_unknown_requests: 2,
      unknown_usage_fields: [
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
      ],
    }),
    { language: "en" },
  )!;
  const rows = Object.fromEntries(snap.shares.map((row) => [row.key, row]));
  expect(rows.input).toMatchObject({ tokens: 2163860, reported: false });
  expect(rows.output).toMatchObject({ tokens: 529631 });
  expect(rows.cacheRead).toMatchObject({ tokens: 9121344 });
  expect(rows.cacheWrite.tokens).toBe(0);
  expect(snap.sharesKnown).toBe(true);
  expect(snap.cacheHitRate).toBeCloseTo(9121344 / 11285204);
});

test("missing or invalid values for all four counters do not invent an input zero", () => {
  for (const value of [undefined, null, false, Number.NaN, -1]) {
    const snap = buildTodayUsageSnapshot(
      stats({
        total_input_tokens: value as number,
        total_output_tokens: value as number,
        total_cache_read_tokens: value as number,
        total_cache_creation_tokens: value as number,
      }),
      { language: "en" },
    )!;
    expect(snap.sharesKnown).toBe(false);
    expect(snap.shares.find((row) => row.key === "input")?.tokens).toBeNull();
    expect(snap.shares.every((row) => row.tokens === null)).toBe(true);
    expect(snap.cacheHitRate).toBeNull();
  }
});

test("four reported zeros remain usable counts rather than missing values", () => {
  const snap = buildTodayUsageSnapshot(
    stats({
      total_input_tokens: 0,
      total_output_tokens: 0,
      total_cache_read_tokens: 0,
      total_cache_creation_tokens: 0,
    }),
    { language: "en" },
  )!;
  expect(snap.sharesKnown).toBe(true);
  expect(snap.shares.every((row) => row.tokens === 0 && row.share === 0)).toBe(
    true,
  );
  expect(snap.cacheHitRate).toBeNull();
});
