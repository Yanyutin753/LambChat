/** @vitest-environment jsdom */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const { steer } = vi.hoisted(() => ({ steer: vi.fn() }));
vi.mock("../../../services/api", () => ({
  sessionApi: {
    steer,
    cancelSteer: vi.fn().mockResolvedValue(undefined),
  },
}));

import { useSteerQueue } from "../steerQueue";

beforeEach(() => {
  sessionStorage.clear();
  steer.mockClear();
});

test("queueFollowUp keeps the message local instead of enqueuing a backend steer", () => {
  const { result } = renderHook(() =>
    useSteerQueue({
      sessionIdRef: { current: "session-1" },
      deferSteer: vi.fn(),
      removeDeferredSteer: vi.fn(),
    }),
  );

  act(() => {
    result.current.queueFollowUp("等这轮结束后再问");
  });

  // 走后端 /steer 会在下一次模型调用被注入（打断当前任务），
  // 追加模式必须只留在本地等 run 结束补发
  expect(steer).not.toHaveBeenCalled();
  expect(result.current.steerMessages).toHaveLength(1);
  expect(result.current.steerMessages[0]).toMatchObject({
    content: "等这轮结束后再问",
    queued: true,
    status: "deferred",
    deferred: true,
  });
});

test("queueFollowUp supports stacking multiple follow-ups in order", () => {
  const { result } = renderHook(() =>
    useSteerQueue({
      sessionIdRef: { current: "session-1" },
      deferSteer: vi.fn(),
      removeDeferredSteer: vi.fn(),
    }),
  );

  act(() => {
    result.current.queueFollowUp("第一条追加");
  });
  act(() => {
    result.current.queueFollowUp("第二条追加");
  });

  expect(steer).not.toHaveBeenCalled();
  expect(result.current.steerMessages.map((item) => item.content)).toEqual([
    "第一条追加",
    "第二条追加",
  ]);
});

test("a steer rejected after a restored run ended stays eligible for idle promotion", async () => {
  steer.mockRejectedValueOnce({ status: 409 });
  const deferred: string[] = [];
  const { result } = renderHook(() =>
    useSteerQueue({
      sessionIdRef: { current: "session-1" },
      deferSteer: (content) => {
        deferred.push(content);
      },
    }),
  );
  await act(async () => {
    await result.current.steerMessage("轮次之间的补充");
  });
  expect(result.current.steerMessages).toHaveLength(1);
  expect(result.current.steerMessages[0]).toMatchObject({
    content: "轮次之间的补充",
    queued: true,
    status: "deferred",
  });
  expect(deferred).toEqual([]);
});

test("a late steer rejection preserves its fallback in the original session queue", async () => {
  let reject!: (error: unknown) => void;
  steer.mockReturnValueOnce(
    new Promise((_resolve, fail) => {
      reject = fail;
    }),
  );
  const sessionIdRef = { current: "session-a" };
  const { result } = renderHook(() =>
    useSteerQueue({ sessionIdRef, deferSteer: vi.fn() }),
  );
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.steerMessage("A 的补充");
  });
  act(() => {
    result.current.clearSteerMessages();
    sessionIdRef.current = "session-b";
    result.current.restoreSteerMessages("session-b");
    result.current.queueFollowUp("B 的补充");
  });
  await act(async () => {
    reject({ status: 409 });
    await sending;
  });
  expect(result.current.steerMessages.map((item) => item.content)).toEqual([
    "B 的补充",
  ]);
  expect(
    JSON.parse(
      sessionStorage.getItem("lambchat:queued-follow-ups:v1:session-a") || "[]",
    ),
  ).toEqual([
    expect.objectContaining({
      content: "A 的补充",
      queued: true,
      status: "deferred",
    }),
  ]);
  act(() => {
    sessionIdRef.current = "session-a";
    result.current.restoreSteerMessages("session-a");
  });
  expect(result.current.steerMessages[0]).toMatchObject({
    content: "A 的补充",
    queued: true,
    status: "deferred",
  });
});

test("a late steer rejection cannot resurrect an explicitly cancelled draft", async () => {
  let reject!: (error: unknown) => void;
  steer.mockReturnValueOnce(
    new Promise((_resolve, fail) => {
      reject = fail;
    }),
  );
  const { result } = renderHook(() =>
    useSteerQueue({
      sessionIdRef: { current: "session-a" },
      deferSteer: vi.fn(),
    }),
  );
  let sending!: Promise<void>;
  act(() => {
    sending = result.current.steerMessage("撤回补充");
  });
  const item = result.current.steerMessages[0];
  act(() => result.current.cancelSteer(item.content, item.id));
  await act(async () => {
    reject({ status: 409 });
    await sending;
  });
  expect(result.current.steerMessages).toEqual([]);
});
