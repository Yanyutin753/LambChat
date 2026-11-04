/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
const api = vi.hoisted(() => ({ getStatus: vi.fn(), resumeQueue: vi.fn() }));
vi.mock("../../../services/api", () => ({ sessionApi: api }));
import { useQueuePause } from "../queuePause";
beforeEach(() => {
  vi.resetAllMocks();
  sessionStorage.clear();
  api.getStatus.mockResolvedValue({
    run_id: "r1",
    queue_paused: true,
    queue_pause_token: "p1",
  });
});

test("a failed resume retains the pause and its queued input", async () => {
  const { result } = renderHook(() => useQueuePause({ current: "s1" }));
  act(() => result.current.setQueuePaused("s1", true, "r1"));
  api.resumeQueue.mockRejectedValueOnce(new Error("offline"));
  await act(async () => {
    await expect(result.current.resumeQueue()).rejects.toThrow("offline");
  });
  expect(result.current.queuePaused).toBe(true);
  expect(result.current.queueResuming).toBe(false);
});

test("a late resume acknowledgement cannot undo a newer stop on the same run", async () => {
  let accept!: () => void;
  api.resumeQueue.mockReturnValueOnce(
    new Promise<void>((resolve) => {
      accept = resolve;
    }),
  );
  const { result } = renderHook(() => useQueuePause({ current: "s1" }));
  act(() => result.current.setQueuePaused("s1", true, "r1"));
  let pending!: Promise<void>;
  await act(async () => {
    pending = result.current.resumeQueue();
    await Promise.resolve();
  });
  act(() => result.current.setQueuePaused("s1", true, "r1"));
  await act(async () => {
    accept();
    await pending;
  });
  expect(result.current.queuePaused).toBe(true);
});

test("duplicate resume clicks send one run-fenced request and do not affect another chat", async () => {
  let accept!: () => void;
  api.resumeQueue.mockReturnValueOnce(
    new Promise<void>((resolve) => {
      accept = resolve;
    }),
  );
  const sessionIdRef = { current: "s1" };
  const { result, rerender } = renderHook(() => useQueuePause(sessionIdRef));
  act(() => result.current.setQueuePaused("s1", true, "r1"));
  let pending!: Promise<void>;
  await act(async () => {
    pending = result.current.resumeQueue();
    void result.current.resumeQueue();
    await Promise.resolve();
  });
  sessionIdRef.current = "s2";
  act(() => result.current.setQueuePaused("s2", true, "r2"));
  rerender();
  await act(async () => {
    accept();
    await pending;
  });
  expect(api.resumeQueue).toHaveBeenCalledTimes(1);
  expect(api.resumeQueue).toHaveBeenCalledWith("s1", "r1", "p1");
  expect(result.current.queuePaused).toBe(true);
});

test("an unconfirmed submission stays paused after reloading the conversation", () => {
  const first = renderHook(() => useQueuePause({ current: "reload-paused" }));
  act(() =>
    first.result.current.setQueuePaused(
      "reload-paused",
      true,
      "r1",
      "delivery",
    ),
  );
  first.unmount();
  const restored = renderHook(() =>
    useQueuePause({ current: "reload-paused" }),
  );
  expect(restored.result.current.queuePaused).toBe(true);
  expect(restored.result.current.queuePauseReason).toBe("delivery");
});

test("continuing after an uncertain delivery can follow a newer unpaused run", async () => {
  const { result } = renderHook(() => useQueuePause({ current: "s1" }));
  act(() => result.current.setQueuePaused("s1", true, "r1", "delivery"));
  api.getStatus.mockResolvedValueOnce({ run_id: "r2", queue_paused: false });
  await act(async () => {
    await result.current.resumeQueue();
  });
  expect(result.current.queuePaused).toBe(false);
  expect(api.resumeQueue).not.toHaveBeenCalled();
});

test("an uncertain delivery cannot resume a newer server pause", async () => {
  const { result } = renderHook(() => useQueuePause({ current: "s1" }));
  act(() => result.current.setQueuePaused("s1", true, "r1", "delivery"));
  api.getStatus.mockResolvedValueOnce({
    run_id: "r2",
    queue_paused: true,
    queue_pause_token: "p2",
  });
  await act(async () => {
    await expect(result.current.resumeQueue()).rejects.toThrow(
      "Queue run changed",
    );
  });
  expect(result.current.queuePaused).toBe(true);
  expect(api.resumeQueue).not.toHaveBeenCalled();
});
