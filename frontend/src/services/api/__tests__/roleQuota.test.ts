import { expect, test, vi } from "vitest";
import { roleApi } from "../role";
const { authFetch } = vi.hoisted(() => ({ authFetch: vi.fn() }));
vi.mock("../fetch", () => ({ authFetch }));

test("role quotas use the dedicated PATCH endpoint with USD limits only", async () => {
  const role = { id: "admin", is_system: true };
  authFetch.mockResolvedValueOnce(role);
  const limits = { five_hour_budget_usd: 0, weekly_budget_usd: null };
  expect(await roleApi.updateQuota("admin", limits)).toEqual(role);
  expect(authFetch).toHaveBeenCalledWith("/api/roles/admin/usage-quota", {
    method: "PATCH",
    body: JSON.stringify(limits),
  });
});
