import { expect, test, vi } from "vitest";
import { usageApi } from "../usage";
const { authFetch } = vi.hoisted(() => ({
  authFetch: vi.fn().mockResolvedValue({}),
}));
vi.mock("../fetch", () => ({ authFetch }));

test("assistant attribution is included in logs, statistics and dashboard requests", async () => {
  await usageApi.list({ assistant_id: "helper" });
  await usageApi.getStats({ assistant_id: "helper" });
  await usageApi.getDashboard({ assistant_id: "helper" });
  expect(authFetch.mock.calls).toHaveLength(3);
  for (const [url] of authFetch.mock.calls)
    expect(url).toContain("assistant_id=helper");
});
