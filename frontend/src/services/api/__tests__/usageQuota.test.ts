import { expect, test, vi } from "vitest";
import { usageApi, type UsageQuota } from "../usage";
const { authFetch } = vi.hoisted(() => ({ authFetch: vi.fn() }));
vi.mock("../fetch", () => ({ authFetch }));

function quotaSnapshot(): UsageQuota {
  const window = {
    limit_usd: null,
    remaining_usd: null,
    used_usd: 0,
    reserved_usd: 0,
    reset_at: null,
    blocked: false,
    unknown: false,
  };
  return {
    currency: "USD",
    timezone: "Asia/Shanghai",
    five_hour: { ...window },
    weekly: { ...window },
  };
}

test("quota always requests the authenticated user's own quota", async () => {
  const quota = quotaSnapshot();
  authFetch.mockResolvedValueOnce(quota);
  expect(await usageApi.getQuota()).toEqual(quota);
  expect(authFetch).toHaveBeenCalledWith("/api/usage/quota");
});

test("quota resets and cards target the explicit user and preserve operation IDs", async () => {
  authFetch
    .mockResolvedValueOnce(quotaSnapshot())
    .mockResolvedValue({ outcome: "reset" });
  await usageApi.getUserQuota("user/one");
  expect(authFetch).toHaveBeenLastCalledWith(
    "/api/usage/users/user%2Fone/quota",
  );
  await usageApi.resetUserQuota("user/one", "weekly", "reset-key");
  expect(authFetch).toHaveBeenLastCalledWith(
    "/api/usage/users/user%2Fone/quota/reset",
    {
      method: "POST",
      body: JSON.stringify({ window: "weekly", idempotency_key: "reset-key" }),
    },
  );
  authFetch.mockResolvedValueOnce({ outcome: "issued", credit_id: "card-one" });
  await usageApi.issueResetCard("user/one", "issue-key");
  expect(authFetch).toHaveBeenLastCalledWith(
    "/api/usage/users/user%2Fone/quota/reset-cards",
    {
      method: "POST",
      body: JSON.stringify({
        idempotency_key: "issue-key",
        window: "five_hour",
      }),
    },
  );
  await usageApi.consumeResetCard("consume-key", "card-one");
  expect(authFetch).toHaveBeenLastCalledWith(
    "/api/usage/quota/reset-cards/consume",
    {
      method: "POST",
      body: JSON.stringify({
        idempotency_key: "consume-key",
        credit_id: "card-one",
      }),
    },
  );
});

test("quota requests forward their cancellation signal", async () => {
  const controller = new AbortController();
  authFetch.mockResolvedValue(quotaSnapshot());
  await usageApi.getQuota(controller.signal);
  expect(authFetch).toHaveBeenLastCalledWith("/api/usage/quota", {
    signal: controller.signal,
  });
});

test.each([
  null,
  {},
  "<!doctype html>",
  { currency: "USD", timezone: "Asia/Shanghai", five_hour: {}, weekly: {} },
])("quota rejects invalid response bodies: %j", async (body) => {
  authFetch.mockResolvedValue(body);
  await expect(usageApi.getQuota()).rejects.toThrow();
});

test.each([null, {}, { outcome: "unexpected" }])(
  "quota mutations reject malformed acknowledgements so callers retain retry keys: %j",
  async (body) => {
    authFetch.mockResolvedValue(body);
    await expect(
      usageApi.resetUserQuota("target", "weekly", "reset-key"),
    ).rejects.toThrow();
    await expect(
      usageApi.issueResetCard("target", "issue-key"),
    ).rejects.toThrow();
    await expect(
      usageApi.consumeResetCard("consume-key", "card-one"),
    ).rejects.toThrow();
  },
);

test("card issuance requires the committed card identity in its acknowledgement", async () => {
  authFetch.mockResolvedValue({ outcome: "issued" });
  await expect(
    usageApi.issueResetCard("target", "issue-key"),
  ).rejects.toThrow();
});

test("zero caps and balances are valid quota values", async () => {
  const quota = quotaSnapshot();
  quota.five_hour = {
    ...quota.five_hour,
    limit_usd: 0,
    remaining_usd: 0,
    blocked: true,
  };
  authFetch.mockResolvedValue(quota);
  expect(await usageApi.getQuota()).toEqual(quota);
});

test("administrative quota GET rejects malformed responses too", async () => {
  authFetch.mockResolvedValue(null);
  await expect(usageApi.getUserQuota("target")).rejects.toThrow();
});

test.each([
  { available_count: 1, credits: null },
  { available_count: -1, credits: [] },
  {
    available_count: 1,
    credits: [{ id: "card", status: "available", expires_at: "invalid" }],
  },
])(
  "quota rejects malformed reset cards without letting the view crash: %j",
  async (reset_credits) => {
    authFetch.mockResolvedValue({ ...quotaSnapshot(), reset_credits });
    await expect(usageApi.getQuota()).rejects.toThrow();
  },
);

test("typed reset cards use their own spent pool and weekly cards include the five-hour pool", async () => {
  const { canRedeemResetCard } = await import("../usage");
  const quota = quotaSnapshot();
  quota.five_hour = {
    ...quota.five_hour,
    limit_usd: 10,
    used_usd: 1,
    unknown: false,
  };
  quota.weekly = {
    ...quota.weekly,
    limit_usd: 20,
    used_usd: 0,
    unknown: false,
  };
  expect(canRedeemResetCard(quota, "five_hour")).toBe(true);
  expect(canRedeemResetCard(quota, "weekly")).toBe(false);
  expect(canRedeemResetCard(quota)).toBe(false);
  quota.weekly.used_usd = 1;
  expect(canRedeemResetCard(quota, "weekly")).toBe(true);
  quota.weekly.unknown = true;
  expect(canRedeemResetCard(quota, "weekly")).toBe(true);
  quota.weekly.used_usd = 20;
  expect(canRedeemResetCard(quota)).toBe(true);
  quota.weekly.used_usd = 0;
  expect(canRedeemResetCard(quota, "weekly")).toBe(false);
});

test.each([
  [{ id: "used", redeemed_at: "invalid" }],
  [{ id: "used", redeemed_at: "2026-10-18T00:00:00Z", window: "other" }],
  null,
])("quota rejects malformed card history: %j", async (history) => {
  authFetch.mockResolvedValue({
    ...quotaSnapshot(),
    reset_credits: { available_count: 0, credits: [], history },
  });
  await expect(usageApi.getQuota()).rejects.toThrow();
});
