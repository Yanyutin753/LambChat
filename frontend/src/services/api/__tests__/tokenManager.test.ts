/** @vitest-environment jsdom */

import { afterEach, expect, test, vi } from "vitest";
import { refreshTokens } from "../tokenManager";
import { setTokens } from "../token";
import { setStoredServerUrl } from "../serverUrlStore";

afterEach(() => {
  localStorage.clear();
  vi.unstubAllGlobals();
});

test("a late refresh from the old server cannot restore credentials after a server switch", async () => {
  setStoredServerUrl("https://old.example.com");
  setTokens("synthetic-old-access", "synthetic-old-refresh");
  let resolve!: (response: Response) => void;
  vi.stubGlobal(
    "fetch",
    vi.fn(
      () =>
        new Promise<Response>((done) => {
          resolve = done;
        }),
    ),
  );

  const pending = refreshTokens();
  setStoredServerUrl("https://new.example.com");
  resolve(
    new Response(
      JSON.stringify({
        access_token: "synthetic-refreshed-access",
        refresh_token: "synthetic-refreshed-refresh",
      }),
      { status: 200 },
    ),
  );

  await expect(pending).rejects.toThrow("Authentication changed");
  expect(localStorage.getItem("access_token")).toBeNull();
  expect(localStorage.getItem("refresh_token")).toBeNull();
});
