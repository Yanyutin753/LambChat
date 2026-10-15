/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
const mocks = vi.hoisted(() => ({ load: vi.fn() }));
vi.mock("../../../../services/api/taskCompletions", () => ({
  getTaskCompletions: mocks.load,
}));
import { useTaskCompletionJournal } from "../taskCompletionJournal";
beforeEach(() => {
  localStorage.clear();
  mocks.load.mockReset();
  mocks.load.mockResolvedValue({ items: [], cursor: null, next_cursor: null });
});

test("reconnect and foreground restore the durable cursor without a status polling timer", async () => {
  mocks.load.mockResolvedValueOnce({
    items: [],
    cursor: "saved",
    next_cursor: null,
  });
  const deliver = vi.fn();
  const { result, unmount } = renderHook(() =>
    useTaskCompletionJournal("user-one", true, deliver),
  );
  await waitFor(() => expect(mocks.load).toHaveBeenCalledOnce());
  await act(async () => {
    await result.current();
  });
  expect(mocks.load.mock.calls.map(([cursor]) => cursor)).toEqual([
    null,
    "saved",
  ]);
  expect(mocks.load.mock.calls[0][1]).toEqual(expect.any(String));
  await act(async () => {
    window.dispatchEvent(new Event("online"));
  });
  expect(mocks.load).toHaveBeenCalledTimes(3);
  unmount();
  await act(async () => {
    window.dispatchEvent(new Event("online"));
  });
  expect(mocks.load).toHaveBeenCalledTimes(3);
});

test("switching account during a request discards the late completion page", async () => {
  let resolve!: (value: unknown) => void;
  mocks.load.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r;
    }),
  );
  const deliver = vi.fn();
  const { rerender } = renderHook(
    ({ user }) => useTaskCompletionJournal(user, true, deliver),
    { initialProps: { user: "old" } },
  );
  rerender({ user: "new" });
  await act(async () => {
    resolve({
      items: [
        {
          id: "old-event",
          session_id: "old-session",
          run_id: "old-run",
          status: "completed",
        },
      ],
      cursor: "old-cursor",
      next_cursor: null,
    });
  });
  expect(deliver).not.toHaveBeenCalled();
  expect(
    localStorage.getItem("lambchat.taskCompletions.cursor.new"),
  ).toBeNull();
});

afterEach(() => {
  vi.useRealTimers();
});

test("temporary 503 retries from saved cursor and stops after successful delivery", async () => {
  vi.useFakeTimers();
  localStorage.setItem("lambchat.taskCompletions.cursor.user-one", "saved");
  mocks.load.mockRejectedValueOnce({ status: 503 }).mockResolvedValueOnce({
    items: [{ id: "done", session_id: "s", run_id: "r", status: "completed" }],
    cursor: "done",
    next_cursor: null,
  });
  const deliver = vi.fn().mockResolvedValue(undefined);
  const { unmount } = renderHook(() =>
    useTaskCompletionJournal("user-one", true, deliver),
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(2000);
  });
  expect(mocks.load.mock.calls.map(([cursor]) => cursor)).toEqual([
    "saved",
    "saved",
  ]);
  expect(deliver).toHaveBeenCalledOnce();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000);
  });
  expect(mocks.load).toHaveBeenCalledTimes(2);
  unmount();
});

test("persistent 503 exhausts three retries until an external wake", async () => {
  vi.useFakeTimers();
  mocks.load.mockRejectedValue({ status: 503 });
  const { unmount } = renderHook(() =>
    useTaskCompletionJournal("user-one", true, vi.fn()),
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000);
  });
  expect(mocks.load).toHaveBeenCalledTimes(4);
  await act(async () => {
    window.dispatchEvent(new Event("online"));
  });
  expect(mocks.load).toHaveBeenCalledTimes(5);
  unmount();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000);
  });
  expect(mocks.load).toHaveBeenCalledTimes(5);
});

test.each([401, 403, 500])(
  "does not automatically retry status %s",
  async (status) => {
    vi.useFakeTimers();
    mocks.load.mockRejectedValue({ status });
    const { unmount } = renderHook(() =>
      useTaskCompletionJournal("user-one", true, vi.fn()),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000);
    });
    expect(mocks.load).toHaveBeenCalledOnce();
    unmount();
  },
);

test("account switch cancels pending retries from the old account", async () => {
  vi.useFakeTimers();
  mocks.load.mockRejectedValueOnce({ status: 503 });
  const { rerender, unmount } = renderHook(
    ({ user }) => useTaskCompletionJournal(user, true, vi.fn()),
    { initialProps: { user: "old" } },
  );
  await act(async () => {});
  rerender({ user: "new" });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(60000);
  });
  expect(mocks.load).toHaveBeenCalledTimes(2);
  unmount();
});
