import { vi } from "vitest";
import { authFetch } from "../fetch";
import { scheduledTaskApi } from "../scheduledTask";

vi.mock("../fetch", () => ({
  authFetch: vi.fn().mockResolvedValue({ items: [], total: 0 }),
}));

test("task search sends trimmed literal text with status and pagination", async () => {
  await scheduledTaskApi.list(20, 20, "paused", { search: " Daily.* " });
  const url = new URL(
    vi.mocked(authFetch).mock.calls.at(-1)![0] as string,
    "http://localhost",
  );
  expect(Object.fromEntries(url.searchParams)).toEqual({
    skip: "20",
    limit: "20",
    status: "paused",
    search: "Daily.*",
  });
});
