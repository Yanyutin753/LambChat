import { expect, test, vi } from "vitest";
import { authFetch } from "../fetch";
import { pushApi } from "../push";

vi.mock("../fetch", () => ({ authFetch: vi.fn() }));

test("older servers without subscription-status preserve existing subscription behavior", async () => {
  vi.mocked(authFetch).mockRejectedValueOnce({ status: 404 });
  await expect(
    pushApi.getSubscriptionStatus("https://push/private"),
  ).resolves.toEqual({ registered: true });
});

test("subscription status does not hide authentication failures", async () => {
  vi.mocked(authFetch).mockRejectedValueOnce({ status: 401 });
  await expect(
    pushApi.getSubscriptionStatus("https://push/private"),
  ).rejects.toEqual({ status: 401 });
});
