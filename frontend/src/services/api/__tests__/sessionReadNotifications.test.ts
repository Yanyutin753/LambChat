/** @vitest-environment jsdom */
import { afterEach, expect, test, vi } from "vitest";
import { sessionApi, SESSIONS_READ_EVENT } from "../session";
import { authFetch } from "../fetch";
import { clearTokens, setTokens } from "../token";

vi.mock("../fetch", () => ({ authFetch: vi.fn() }));
afterEach(() => {
  vi.resetAllMocks();
  clearTokens();
});

for (const scope of [
  undefined,
  { projectId: "project-one" },
  { scheduledTaskId: "schedule-one" },
]) {
  test(`successful mark all read publishes its scope ${JSON.stringify(
    scope,
  )}`, async () => {
    vi.mocked(authFetch).mockResolvedValue({ status: "ok", modified_count: 1 });
    const listener = vi.fn();
    window.addEventListener(SESSIONS_READ_EVENT, listener, { once: true });
    await sessionApi.markAllRead(scope);
    expect(listener).toHaveBeenCalledOnce();
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual(
      scope ?? {},
    );
  });
}

test("a failed mark all read does not clear task notifications", async () => {
  vi.mocked(authFetch).mockRejectedValue(new Error("offline"));
  const listener = vi.fn();
  window.addEventListener(SESSIONS_READ_EVENT, listener);
  try {
    await expect(sessionApi.markAllRead()).rejects.toThrow("offline");
    expect(listener).not.toHaveBeenCalled();
  } finally {
    window.removeEventListener(SESSIONS_READ_EVENT, listener);
  }
});

test("reading one session publishes only that session", async () => {
  vi.mocked(authFetch).mockResolvedValue(undefined);
  const listener = vi.fn();
  window.addEventListener(SESSIONS_READ_EVENT, listener, { once: true });
  await sessionApi.markRead("session-one");
  expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual({
    sessionId: "session-one",
  });
});

const accountToken = (subject: string, revision = 1) =>
  `header.${btoa(JSON.stringify({ sub: subject, revision }))}.signature`;

test.each(["all", "single"])(
  "a late %s read response cannot clear a newly signed-in account",
  async (scope) => {
    let finish!: (value: { status: string; modified_count: number }) => void;
    vi.mocked(authFetch).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    setTokens(accountToken("old"), "refresh-old");
    const reads: unknown[] = [];
    const listener = (event: Event) =>
      reads.push((event as CustomEvent).detail);
    window.addEventListener(SESSIONS_READ_EVENT, listener);
    try {
      const request =
        scope === "all"
          ? sessionApi.markAllRead()
          : sessionApi.markRead("session-one");
      clearTokens();
      setTokens(accountToken("new"), "refresh-new");
      finish({ status: "ok", modified_count: 1 });
      await request;
      expect(reads).toEqual([]);
    } finally {
      window.removeEventListener(SESSIONS_READ_EVENT, listener);
    }
  },
);

test.each(["all", "single"])(
  "a %s read response still updates the same account after token refresh",
  async (scope) => {
    let finish!: (value: { status: string; modified_count: number }) => void;
    vi.mocked(authFetch).mockReturnValueOnce(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    setTokens(accountToken("same"), "refresh-one");
    const reads: unknown[] = [];
    const listener = (event: Event) =>
      reads.push((event as CustomEvent).detail);
    window.addEventListener(SESSIONS_READ_EVENT, listener);
    try {
      const request =
        scope === "all"
          ? sessionApi.markAllRead()
          : sessionApi.markRead("session-one");
      setTokens(accountToken("same", 2), "refresh-two");
      finish({ status: "ok", modified_count: 1 });
      await request;
      expect(reads).toEqual(
        scope === "all" ? [{}] : [{ sessionId: "session-one" }],
      );
    } finally {
      window.removeEventListener(SESSIONS_READ_EVENT, listener);
    }
  },
);
