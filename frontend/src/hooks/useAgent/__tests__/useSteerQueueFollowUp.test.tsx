/** @vitest-environment jsdom */

import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const steer = vi.fn();
vi.mock("../../services/api", () => ({
  sessionApi: {
    steer,
    cancelSteer: vi.fn(),
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
