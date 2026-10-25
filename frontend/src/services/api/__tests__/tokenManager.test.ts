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

test("a stranded refresh times out without logging out and releases all callers for retry", async () => {
  vi.useFakeTimers();
  try {
    setTokens("synthetic-access", "synthetic-refresh");
    const fetcher = vi.fn(
      (_url, init: RequestInit) =>
        new Promise<Response>((_resolve, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );
    vi.stubGlobal("fetch", fetcher);
    const first = refreshTokens().catch((error) => error);
    const second = refreshTokens().catch((error) => error);
    await vi.advanceTimersByTimeAsync(15_000);
    expect(fetcher.mock.calls[0][1].signal?.aborted).toBe(true);
    expect((await first).name).toBe("AbortError");
    expect((await second).name).toBe("AbortError");
    expect(fetcher).toHaveBeenCalledOnce();
    expect(localStorage.getItem("refresh_token")).toBe("synthetic-refresh");
    fetcher.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          access_token: "new-access",
          refresh_token: "new-refresh",
        }),
      ),
    );
    await expect(refreshTokens()).resolves.toEqual({
      access_token: "new-access",
      refresh_token: "new-refresh",
    });
  } finally {
    vi.useRealTimers();
  }
});
