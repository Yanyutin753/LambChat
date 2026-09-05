import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("../fetch", () => ({ authFetch: mocks.authFetch }));

import { sandboxApi } from "../sandbox.ts";

beforeEach(() => {
  mocks.authFetch.mockReset();
});

test("getSandboxStatus fetches the daemon online status", async () => {
  mocks.authFetch.mockResolvedValueOnce({
    online: true,
    client_id: "abc123",
    daemon_version: "0.1.0",
  });

  const status = await sandboxApi.getStatus();

  expect(status).toEqual({
    online: true,
    client_id: "abc123",
    daemon_version: "0.1.0",
  });
  expect(mocks.authFetch).toHaveBeenCalledWith("/api/sandbox/status");
});

test("getSandboxStatus tolerates the offline minimal payload", async () => {
  mocks.authFetch.mockResolvedValueOnce({ online: false });

  await expect(sandboxApi.getStatus()).resolves.toEqual({ online: false });
});

test("createPat posts a sandbox-scoped personal access token", async () => {
  mocks.authFetch.mockResolvedValueOnce({
    token: "lcpat_token",
    pat_id: "pat-1",
  });

  const created = await sandboxApi.createPat("lambchat-desktop-shell");

  expect(created).toEqual({ token: "lcpat_token", pat_id: "pat-1" });
  expect(mocks.authFetch).toHaveBeenCalledWith("/api/auth/pat", {
    method: "POST",
    body: JSON.stringify({
      name: "lambchat-desktop-shell",
      scopes: ["sandbox:execute"],
    }),
  });
});
