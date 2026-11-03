import { afterEach, expect, test, vi } from "vitest";
import { authFetch } from "../fetch";
import { versionApi } from "../version";
import { authApi } from "../auth";
import { scheduledTaskApi } from "../scheduledTask";

vi.mock("../tokenManager", () => ({
  getValidAccessToken: async () => "test-token",
}));

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test.each(["headers", "body"])(
  "JSON request timeout also covers stalled %s",
  async (stage) => {
    vi.useFakeTimers();
    let signal!: AbortSignal;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url, init) => {
        signal = init.signal;
        const stalled = new Promise((_, reject) => {
          signal.addEventListener("abort", () => reject(signal.reason), {
            once: true,
          });
        });
        return stage === "headers"
          ? stalled
          : Promise.resolve({
              ok: true,
              status: 200,
              headers: new Headers(),
              text: () => stalled,
            });
      }),
    );
    const request = authFetch("/api/test", { skipAuth: true, timeoutMs: 100 });
    const assertion = expect(request).rejects.toMatchObject({
      name: "TimeoutError",
    });
    await vi.advanceTimersByTimeAsync(100);
    expect(signal.aborted).toBe(true);
    await assertion;
    expect(vi.getTimerCount()).toBe(0);
  },
);

test("caller cancellation is preserved and successful requests release the timer", async () => {
  vi.useFakeTimers();
  const controller = new AbortController();
  controller.abort();
  const fetchMock = vi.fn((_url, init) =>
    init.signal.aborted
      ? Promise.reject(init.signal.reason)
      : Promise.resolve(new Response("{}")),
  );
  vi.stubGlobal("fetch", fetchMock);
  await expect(
    authFetch("/api/test", {
      skipAuth: true,
      timeoutMs: 100,
      signal: controller.signal,
    }),
  ).rejects.toMatchObject({ name: "AbortError" });
  await authFetch("/api/test", { skipAuth: true, timeoutMs: 100 });
  expect(vi.getTimerCount()).toBe(0);
});

test.each([
  ["startup profile", () => authApi.getCurrentUser()],
  ["version", () => versionApi.get()],
  ["update check", () => versionApi.checkForUpdates()],
  ["schedule refresh", () => scheduledTaskApi.listBySession("chat-1")],
  ["schedule save", () => scheduledTaskApi.update("task-1", { name: "Retry" })],
  ["schedule action", () => scheduledTaskApi.runNow("task-1")],
])("%s cannot wait indefinitely for a response", async (_name, request) => {
  vi.useFakeTimers();
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (_url, init) =>
        new Promise((_, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(init.signal.reason),
          );
        }),
    ),
  );
  const assertion = expect(request()).rejects.toMatchObject({
    name: "TimeoutError",
  });
  await vi.advanceTimersByTimeAsync(30_000);
  await assertion;
});
