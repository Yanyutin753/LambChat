import { beforeEach, expect, test, vi } from "vitest";
import { usageApi } from "../usage";
const { authFetch } = vi.hoisted(() => ({ authFetch: vi.fn() }));
vi.mock("../fetch", () => ({ authFetch }));
const batch = {
  id: "batch/one",
  window: "weekly",
  status: "completed",
  total: 2,
  processed: 2,
  issued: 2,
  failed: 0,
  errors: [],
};
beforeEach(() => authFetch.mockReset().mockResolvedValue(batch));
test("batch API preserves the chosen window and retry key and encodes batch IDs", async () => {
  const signal = new AbortController().signal;
  await usageApi.createResetCardBatch("weekly", "same-key", signal);
  expect(authFetch).toHaveBeenLastCalledWith(
    "/api/usage/quota/reset-card-batches",
    {
      method: "POST",
      body: JSON.stringify({ window: "weekly", idempotency_key: "same-key" }),
      signal,
    },
  );
  await usageApi.getResetCardBatch("batch/one", signal);
  expect(authFetch).toHaveBeenLastCalledWith(
    "/api/usage/quota/reset-card-batches/batch%2Fone",
    { signal },
  );
  await usageApi.advanceResetCardBatch("batch/one", signal);
  expect(authFetch).toHaveBeenLastCalledWith(
    "/api/usage/quota/reset-card-batches/batch%2Fone/advance",
    { method: "POST", signal },
  );
  authFetch.mockResolvedValueOnce({ items: [batch] });
  expect(await usageApi.listResetCardBatches(signal)).toEqual({
    items: [batch],
  });
  expect(authFetch).toHaveBeenLastCalledWith(
    "/api/usage/quota/reset-card-batches?limit=1",
    { signal },
  );
});
test.each([
  null,
  {},
  { ...batch, total: -1 },
  { ...batch, processed: 3 },
  { ...batch, issued: 1 },
  { ...batch, status: "unknown" },
  { ...batch, window: "daily" },
  { ...batch, errors: null },
])("rejects malformed batch acknowledgements: %j", async (body) => {
  authFetch.mockResolvedValue(body);
  await expect(
    usageApi.createResetCardBatch("weekly", "same-key"),
  ).rejects.toThrow();
  await expect(usageApi.advanceResetCardBatch("batch/one")).rejects.toThrow();
});
