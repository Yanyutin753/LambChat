/** @vitest-environment jsdom */
import { renderHook } from "@testing-library/react";
import { useRef } from "react";

import type { Message } from "../../../types/message";
import { useSteerQueue } from "../steerQueue";

test("useSteerQueue returns stable references across renders", () => {
  const setMessages = (updater: (prev: Message[]) => Message[]) => {
    void updater;
  };
  const setError = (error: string | null) => void error;

  const { result, rerender } = renderHook(() => {
    const sessionIdRef = useRef<string | null>("session-1");
    return useSteerQueue({ sessionIdRef, setMessages, setError });
  });

  const first = result.current;
  rerender();

  // 引用稳定：作为 props 传给 memo(ChatInput) 时不破坏记忆化
  expect(result.current.steerMessage).toBe(first.steerMessage);
  expect(result.current.cancelSteer).toBe(first.cancelSteer);
});
