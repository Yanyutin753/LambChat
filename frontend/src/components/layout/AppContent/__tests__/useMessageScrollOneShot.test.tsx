/** @vitest-environment jsdom */

import { act, renderHook } from "@testing-library/react";
import type { VirtuosoHandle } from "react-virtuoso";
import { afterEach, describe, expect, test, vi } from "vitest";
import { useMessageScroll } from "../useMessageScroll.hook";

type HarnessProps = {
  messages: Array<{
    id: string;
    role: "assistant" | "user";
    isStreaming: boolean;
    parts: [];
    runId: string | null;
  }>;
  sessionId: string | null;
  externalNavigationToken: string | null;
  isLoadingHistory: boolean;
  historyLoadGeneration: number;
};

const historyMessage: HarnessProps["messages"][number] = {
  id: "history-1",
  role: "assistant",
  isStreaming: false,
  parts: [],
  runId: null,
};

function useHarness(props: HarnessProps) {
  const invoke = useMessageScroll as unknown as (
    ...args: unknown[]
  ) => ReturnType<typeof useMessageScroll>;
  return invoke(
    props.messages,
    props.sessionId,
    props.externalNavigationToken,
    null,
    null,
    false,
    false,
    props.isLoadingHistory,
    props.historyLoadGeneration,
    null,
  );
}

function attachVirtuoso(
  ref: React.RefObject<VirtuosoHandle | null>,
  scrollToIndex: ReturnType<typeof vi.fn>,
) {
  ref.current = { scrollToIndex } as unknown as VirtuosoHandle;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("one-shot history positioning", () => {
  test("aligns one accepted history generation exactly once", () => {
    vi.useFakeTimers();
    const scrollToIndex = vi.fn();
    const { result, rerender } = renderHook(useHarness, {
      initialProps: {
        messages: [],
        sessionId: "session-1",
        externalNavigationToken: null,
        isLoadingHistory: true,
        historyLoadGeneration: 1,
      },
    });
    act(() => attachVirtuoso(result.current.virtuosoRef, scrollToIndex));

    rerender({
      messages: [historyMessage],
      sessionId: "session-1",
      externalNavigationToken: null,
      isLoadingHistory: false,
      historyLoadGeneration: 1,
    });
    rerender({
      messages: [historyMessage],
      sessionId: "session-1",
      externalNavigationToken: null,
      isLoadingHistory: false,
      historyLoadGeneration: 1,
    });
    act(() => vi.runOnlyPendingTimers());

    expect(scrollToIndex).toHaveBeenCalledTimes(1);
    expect(scrollToIndex).toHaveBeenCalledWith({
      index: "LAST",
      align: "end",
      behavior: "auto",
    });
  });

  test("consumes a missing-ref generation without retrying later", () => {
    const scrollToIndex = vi.fn();
    const { result, rerender } = renderHook(useHarness, {
      initialProps: {
        messages: [],
        sessionId: "session-1",
        externalNavigationToken: null,
        isLoadingHistory: true,
        historyLoadGeneration: 1,
      },
    });

    rerender({
      messages: [historyMessage],
      sessionId: "session-1",
      externalNavigationToken: null,
      isLoadingHistory: false,
      historyLoadGeneration: 1,
    });
    act(() => attachVirtuoso(result.current.virtuosoRef, scrollToIndex));
    rerender({
      messages: [historyMessage],
      sessionId: "session-1",
      externalNavigationToken: null,
      isLoadingHistory: false,
      historyLoadGeneration: 1,
    });

    expect(scrollToIndex).not.toHaveBeenCalled();
  });

  test("does not align when external navigation arrives after arming", () => {
    const scrollToIndex = vi.fn();
    const { result, rerender } = renderHook(useHarness, {
      initialProps: {
        messages: [],
        sessionId: "session-1",
        externalNavigationToken: null,
        isLoadingHistory: true,
        historyLoadGeneration: 1,
      },
    });
    act(() => attachVirtuoso(result.current.virtuosoRef, scrollToIndex));

    rerender({
      messages: [historyMessage],
      sessionId: "session-1",
      externalNavigationToken: "target-1",
      isLoadingHistory: false,
      historyLoadGeneration: 1,
    });

    expect(scrollToIndex).not.toHaveBeenCalled();
  });

  test("infers one batched history completion only when generation changes", () => {
    const scrollToIndex = vi.fn();
    const { result, rerender } = renderHook(useHarness, {
      initialProps: {
        messages: [],
        sessionId: "session-1",
        externalNavigationToken: null,
        isLoadingHistory: false,
        historyLoadGeneration: 1,
      },
    });
    act(() => attachVirtuoso(result.current.virtuosoRef, scrollToIndex));

    rerender({
      messages: [historyMessage],
      sessionId: "session-2",
      externalNavigationToken: null,
      isLoadingHistory: false,
      historyLoadGeneration: 2,
    });
    expect(scrollToIndex).toHaveBeenCalledTimes(1);

    scrollToIndex.mockClear();
    const ordinary = renderHook(useHarness, {
      initialProps: {
        messages: [],
        sessionId: null,
        externalNavigationToken: null,
        isLoadingHistory: false,
        historyLoadGeneration: 0,
      },
    });
    act(() =>
      attachVirtuoso(ordinary.result.current.virtuosoRef, scrollToIndex),
    );
    ordinary.rerender({
      messages: [{ ...historyMessage, id: "first-user", role: "user" }],
      sessionId: "new-session",
      externalNavigationToken: null,
      isLoadingHistory: false,
      historyLoadGeneration: 0,
    });

    // This is the ordinary first-user-message path. It must retain its
    // existing generic bottom behavior even though history inference is off.
    expect(scrollToIndex).toHaveBeenCalled();
  });
});
