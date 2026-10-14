/** @vitest-environment jsdom */
import { afterEach, expect, test, vi } from "vitest";
import { sessionApi, SESSIONS_READ_EVENT } from "../session";
import { authFetch } from "../fetch";

vi.mock("../fetch", () => ({ authFetch: vi.fn() }));
afterEach(() => vi.resetAllMocks());

for (const scope of [undefined, {projectId:"project-one"}, {scheduledTaskId:"schedule-one"}]) {
  test(`successful mark all read publishes its scope ${JSON.stringify(scope)}`, async () => {
    vi.mocked(authFetch).mockResolvedValue({status:"ok",modified_count:1});
    const listener = vi.fn();
    window.addEventListener(SESSIONS_READ_EVENT, listener, {once:true});
    await sessionApi.markAllRead(scope);
    expect(listener).toHaveBeenCalledOnce();
    expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual(scope ?? {});
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
  window.addEventListener(SESSIONS_READ_EVENT, listener, {once:true});
  await sessionApi.markRead("session-one");
  expect((listener.mock.calls[0][0] as CustomEvent).detail).toEqual({sessionId:"session-one"});
});
