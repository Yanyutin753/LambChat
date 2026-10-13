import { vi } from "vitest";
import { authFetch } from "../fetch";
import { sessionApi } from "../session";
vi.mock("../fetch", () => ({ authFetch: vi.fn() }));

test("persistent goal API uses session scope and sends revision for updates", async () => {
  vi.mocked(authFetch).mockResolvedValue({ goal: null });
  await sessionApi.getPersistentGoal("session/1");
  expect(authFetch).toHaveBeenLastCalledWith("/api/chat/sessions/session%2F1/goal", undefined);
  await sessionApi.putPersistentGoal("session/1", { objective: "docs", rubric: "verified", expected_revision: 2 });
  expect(authFetch).toHaveBeenLastCalledWith("/api/chat/sessions/session%2F1/goal", { method: "PUT", body: JSON.stringify({ objective: "docs", rubric: "verified", expected_revision: 2 }) });
  await sessionApi.controlPersistentGoal("session/1", "pause");
  expect(authFetch).toHaveBeenLastCalledWith("/api/chat/sessions/session%2F1/goal/pause", { method: "POST" });
});
