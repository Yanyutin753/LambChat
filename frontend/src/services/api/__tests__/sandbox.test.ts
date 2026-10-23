import { afterEach, beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  authFetch: vi.fn(),
}));

vi.mock("../fetch", () => ({ authFetch: mocks.authFetch }));

import { sandboxApi } from "../sandbox.ts";

beforeEach(() => {
  mocks.authFetch.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("getSandboxStatus fetches the daemon online status", async () => {
  mocks.authFetch.mockResolvedValueOnce({
    online: true,
    client_id: "abc123",
    daemon_version: "0.2.0",
    daemon_confirm_policy: "commands",
  });

  const status = await sandboxApi.getStatus();

  expect(status).toEqual({
    online: true,
    client_id: "abc123",
    daemon_version: "0.2.0",
    daemon_confirm_policy: "commands",
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

// ---------- 配对流：无副作用登录 / 指定账号铸 PAT / PAT 自撤销（M4 T7） ----------

test("pairingLogin logs in via plain fetch and returns only the access token", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(
      JSON.stringify({
        access_token: "pairing-jwt",
        refresh_token: "should-be-ignored",
        token_type: "bearer",
      }),
      { status: 200 },
    ),
  );
  vi.stubGlobal("fetch", fetchMock);

  await expect(
    sandboxApi.pairingLogin({ username: "m1_smoke", password: "secret" }),
  ).resolves.toEqual({ access_token: "pairing-jwt" });

  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/api/auth/login");
  expect(init.method).toBe("POST");
  expect(JSON.parse(String(init.body))).toEqual({
    username: "m1_smoke",
    password: "secret",
  });
  // 直连 fetch：绝不走 authFetch（其会附带壳会话 token）
  expect(mocks.authFetch).not.toHaveBeenCalled();
});

test("pairingLogin rejects on failed credentials without resolving a token", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: "invalid_credentials",
            message: "Invalid username or password",
          },
        }),
        { status: 401 },
      ),
    ),
  );

  const err = await sandboxApi
    .pairingLogin({ username: "m1_smoke", password: "wrong" })
    .catch((e: Error & { status?: number; code?: string }) => e);
  expect(err).toBeInstanceOf(Error);
  expect(err.status).toBe(401);
  expect(err.code).toBe("invalid_credentials");
});

test("createPairingPat mints a PAT with the pairing account's bearer token", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ token: "lc_pat_new", pat_id: "p9" }), {
      status: 200,
    }),
  );
  vi.stubGlobal("fetch", fetchMock);

  await expect(sandboxApi.createPairingPat("pairing-jwt")).resolves.toEqual({
    token: "lc_pat_new",
    pat_id: "p9",
  });

  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/api/auth/pat");
  expect(init.method).toBe("POST");
  expect((init.headers as Record<string, string>).Authorization).toBe(
    "Bearer pairing-jwt",
  );
  expect(JSON.parse(String(init.body))).toEqual({
    name: "lambchat-desktop-shell",
    scopes: ["sandbox:execute"],
  });
  expect(mocks.authFetch).not.toHaveBeenCalled();
});

test("revokePairingPat deletes the bearer PAT itself via /current", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), { status: 200 }),
    );
  vi.stubGlobal("fetch", fetchMock);

  await expect(
    sandboxApi.revokePairingPat("lc_pat_old"),
  ).resolves.toBeUndefined();

  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
  expect(url).toBe("/api/auth/pat/current");
  expect(init.method).toBe("DELETE");
  expect((init.headers as Record<string, string>).Authorization).toBe(
    "Bearer lc_pat_old",
  );
});

test("revokePairingPat surfaces structured errors (e.g. already revoked)", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          detail: {
            code: "pat_not_found",
            message: "Personal access token not found or revoked",
          },
        }),
        { status: 401 },
      ),
    ),
  );

  const err = await sandboxApi
    .revokePairingPat("lc_pat_gone")
    .catch((e: Error & { status?: number; code?: string }) => e);
  expect(err.status).toBe(401);
  expect(err.code).toBe("pat_not_found");
});

test("pairingLogin verifies the second factor without changing the shell identity", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          two_factor_required: true,
          challenge_token: "challenge",
        }),
        { status: 200 },
      ),
    )
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          access_token: "verified-pairing-jwt",
          pairing_token: "one-use-grant",
        }),
        { status: 200 },
      ),
    );
  vi.stubGlobal("fetch", fetchMock);
  await expect(
    sandboxApi.pairingLogin({
      username: "account",
      password: "secret",
      code: "123456",
    }),
  ).resolves.toEqual({
    access_token: "verified-pairing-jwt",
    pairing_token: "one-use-grant",
  });
  expect(fetchMock.mock.calls[1][0]).toBe("/api/auth/2fa/verify");
  expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
    challenge_token: "challenge",
    code: "123456",
    for_pairing: true,
  });
  expect(mocks.authFetch).not.toHaveBeenCalled();
});

test("current-account pairing sends fresh proof only on the PAT request", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ token: "pat", pat_id: "id" }), {
      status: 200,
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  await sandboxApi.createPairingPat("current-jwt", { code: "123456" });
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
    name: "lambchat-desktop-shell",
    scopes: ["sandbox:execute"],
    code: "123456",
  });
});
