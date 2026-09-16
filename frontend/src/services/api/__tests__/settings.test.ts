import { vi } from "vitest";
import { settingsApi } from "../settings";
import { authFetch } from "../fetch";

vi.mock("../fetch", () => ({ authFetch: vi.fn() }));

test("reset all sends explicit confirmation to the backend", async () => {
  await settingsApi.resetAll();
  expect(authFetch).toHaveBeenCalledWith("/api/settings/reset", {
    method: "POST",
    body: JSON.stringify({ confirmed: true }),
  });
});
