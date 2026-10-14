/** @vitest-environment jsdom */
import { act, renderHook } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { Message } from "../../../types";

const mocks = vi.hoisted(() => ({ events: vi.fn() }));
vi.mock("../../../services/api", () => ({ sessionApi: { getEvents: mocks.events } }));
import { useHistoryTracePagination } from "../historyTracePagination";

function windowFor(run: string) {
  return {
    events: [{ id: `${run}:user`, timestamp: "2026-10-15T00:00:00Z", event_type: "user:message", run_id: run, data: { content: run } }],
    has_more_traces: true,
    trace_window: { oldest_trace_started_at: "2026-10-15T00:00:00Z", oldest_trace_id: run },
  };
}

function dependencies() {
  return {
    options: undefined,
    sessionIdRef: { current: "A" as string | null },
    isLoadingHistoryRef: { current: false },
    processedEventIdsRef: { current: new Set<string>() },
    messagesRef: { current: [] as Message[] },
    streamingMessageIdRef: { current: null as string | null },
    setMessages: vi.fn(), setGoalsByRunId: vi.fn(),
    loadHistoryRequestIdRef: { current: 0 },
    historyAbortControllerRef: { current: null as AbortController | null },
    setIsLoadingHistory: vi.fn(), setError: vi.fn(),
  };
}

test("older history ignores late A responses after A to B to A and preserves the new loader", async () => {
  let resolveOld!: (value: ReturnType<typeof windowFor>) => void;
  let resolveNew!: (value: ReturnType<typeof windowFor>) => void;
  mocks.events.mockReset()
    .mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; }))
    .mockImplementationOnce(() => new Promise(resolve => { resolveNew = resolve; }));
  const deps = dependencies();
  const { result } = renderHook(() => useHistoryTracePagination(deps));
  act(() => result.current.recordFirstWindow(windowFor("first-A")));
  let oldTask!: Promise<void>;
  act(() => { oldTask = result.current.loadOlderHistory(); });
  const oldSignal = mocks.events.mock.calls[0][1].signal as AbortSignal;
  act(() => {
    deps.sessionIdRef.current = "B";
    result.current.reset();
    deps.sessionIdRef.current = "A";
    result.current.reset();
    result.current.recordFirstWindow(windowFor("current-A"));
  });
  let newTask!: Promise<void>;
  act(() => { newTask = result.current.loadOlderHistory(); });
  await act(async () => { resolveOld(windowFor("stale-old-A")); await oldTask; });
  expect(oldSignal.aborted).toBe(true);
  expect(deps.setMessages).not.toHaveBeenCalled();
  expect(result.current.isLoadingOlderHistory).toBe(true);
  await act(async () => { resolveNew(windowFor("fresh-old-A")); await newTask; });
  expect(deps.setMessages).toHaveBeenCalledOnce();
  expect(deps.setMessages.mock.calls[0][0].map((message: Message) => message.content))
    .toEqual(["fresh-old-A", "current-A"]);
  expect(result.current.isLoadingOlderHistory).toBe(false);
});

test("unmount aborts its older history read", () => {
  mocks.events.mockReset().mockImplementation(() => new Promise(() => {}));
  const { result, unmount } = renderHook(() => useHistoryTracePagination(dependencies()));
  act(() => result.current.recordFirstWindow(windowFor("first-A")));
  act(() => { void result.current.loadOlderHistory(); });
  const signal = mocks.events.mock.calls[0][1].signal as AbortSignal;
  unmount();
  expect(signal.aborted).toBe(true);
});
