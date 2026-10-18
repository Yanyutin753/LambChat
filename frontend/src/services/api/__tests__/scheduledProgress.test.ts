import { expect, test, vi } from "vitest";
import { sessionApi } from "../session";
import { authFetch } from "../fetch";

vi.mock("../config", () => ({ API_BASE: "" }));
vi.mock("../fetch", () => ({
  authFetch: vi.fn().mockResolvedValue({ progress: [] }),
}));

test("scheduled catch-up requests named runs within its encoded parent session", async () => {
  const controller = new AbortController();
  await sessionApi.getScheduledProgress("parent/a", controller.signal, [
    "scheduled-1",
    "scheduled:2",
  ]);
  expect(authFetch).toHaveBeenCalledWith(
    "/api/scheduled-tasks/session/parent%2Fa/progress?run_id=scheduled-1&run_id=scheduled%3A2",
    { signal: controller.signal },
  );
});
