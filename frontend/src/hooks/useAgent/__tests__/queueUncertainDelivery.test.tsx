/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { useSteerFollowUpPromotion, useSteerQueue } from "../steerQueue";
import type { ChatSubmissionCallbacks } from "../types";

const api = vi.hoisted(() => ({
  getStatus: vi.fn(),
  steer: vi.fn(),
  cancelSteer: vi.fn(),
}));
vi.mock("../../../services/api", () => ({ sessionApi: api }));
beforeEach(() => {
  sessionStorage.clear();
  vi.resetAllMocks();
  vi.useFakeTimers();
  api.getStatus.mockResolvedValue({ status: "completed", run_id: "r1" });
  api.cancelSteer.mockResolvedValue({});
});
afterEach(() => vi.useRealTimers());

test("an unconfirmed automatic delivery remains editable after reload and is never auto-retried", async () => {
  const sessionIdRef = { current: "s1" };
  const isSendingRef = { current: false };
  const cancelledSteerIdsRef = { current: new Set<string>() };
  const followUpSteerIdsRef = { current: new Set<string>() };
  const send = vi.fn(
    async (
      _content: string,
      _attachments: unknown,
      callbacks?: ChatSubmissionCallbacks,
    ) => callbacks?.onRejected?.(),
  );
  const sendMessageRef = { current: send };
  const setQueuePaused = vi.fn();
  const { result, unmount } = renderHook(() => {
    const queue = useSteerQueue({ sessionIdRef });
    useSteerFollowUpPromotion({
      sessionIdRef,
      isSendingRef,
      cancelledSteerIdsRef,
      followUpSteerIdsRef,
      sendMessageRef,
      setQueuePaused,
      isLoading: false,
      steerMessages: queue.steerMessages,
      clearSteer: queue.clearSteer,
      markSteerFailed: queue.markSteerFailed,
    });
    return queue;
  });
  act(() => result.current.queueFollowUp("响应丢失也保留我"));
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1);
  });
  expect(result.current.steerMessages[0]).toMatchObject({
    status: "failed",
    queued: false,
  });
  expect(setQueuePaused).toHaveBeenCalledWith("s1", true, "r1", "delivery");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10000);
  });
  expect(send).toHaveBeenCalledTimes(1);
  unmount();
  const restored = renderHook(() => useSteerQueue({ sessionIdRef }));
  expect(restored.result.current.steerMessages[0]).toMatchObject({
    content: "响应丢失也保留我",
    status: "failed",
    queued: false,
  });
});

test("reload during queued guide submission preserves an unconfirmed draft without replaying it", async () => {
  let accept!: () => void;
  api.steer.mockReturnValueOnce(
    new Promise<void>((resolve) => {
      accept = resolve;
    }),
  );
  const sessionIdRef = { current: "s1" };
  const first = renderHook(() => useSteerQueue({ sessionIdRef }));
  act(() => first.result.current.queueFollowUp("引导不能丢"));
  const id = first.result.current.steerMessages[0].id;
  let pending!: Promise<void>;
  act(() => {
    pending = first.result.current.steerMessage("引导不能丢", [], id);
  });
  const restored = renderHook(() => useSteerQueue({ sessionIdRef }));
  expect(restored.result.current.steerMessages[0]).toMatchObject({
    id,
    content: "引导不能丢",
    status: "failed",
    queued: false,
  });
  await act(async () => {
    accept();
    await pending;
  });
  expect(first.result.current.steerMessages[0]).toMatchObject({
    id,
    status: "pending",
    queued: true,
  });
  const acceptedReload = renderHook(() => useSteerQueue({ sessionIdRef }));
  expect(acceptedReload.result.current.steerMessages).toEqual([]);
});

test("server acknowledgement replaces an uncertain draft with the same message ID", async () => {
  api.steer.mockRejectedValueOnce(new Error("response lost"));
  const sessionIdRef = { current: "s1" };
  const { result } = renderHook(() => useSteerQueue({ sessionIdRef }));
  await act(async () => {
    await result.current.steerMessage("已受理但响应丢失");
  });
  const id = result.current.steerMessages[0].id;
  act(() =>
    result.current.hydrateSteers([
      {
        message_id: id,
        content: "已受理但响应丢失",
        created_at: new Date().toISOString(),
      },
    ]),
  );
  expect(result.current.steerMessages).toHaveLength(1);
  expect(result.current.steerMessages[0]).toMatchObject({
    id,
    status: "pending",
    queued: true,
  });
  expect(sessionStorage.getItem("lambchat:queued-follow-ups:v1:s1")).toBeNull();
});

test("delivered history removes the matching uncertain draft without dropping other drafts", async () => {
  api.steer.mockRejectedValueOnce(new Error("response lost"));
  const { result } = renderHook(() =>
    useSteerQueue({ sessionIdRef: { current: "s1" } }),
  );
  await act(async () => {
    await result.current.steerMessage("历史中已送达");
  });
  const deliveredId = result.current.steerMessages[0].id;
  act(() => result.current.queueFollowUp("下一条待发送"));
  act(() => result.current.hydrateSteers([], [deliveredId]));
  expect(result.current.steerMessages.map((item) => item.content)).toEqual([
    "下一条待发送",
  ]);
});
