/** @vitest-environment jsdom */
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { FetchEventSourceInit } from "@microsoft/fetch-event-source";

const mocks = vi.hoisted(() => ({
  stream: vi.fn(),
  get: vi.fn(),
  status: vi.fn(),
  runs: vi.fn(),
  events: vi.fn(),
}));
vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: mocks.stream,
}));
vi.mock("../../useAuth", () => ({
  useAuth: () => ({ hasAnyPermission: () => false, user: { id: "owner" } }),
}));
vi.mock("../../../services/api", () => ({
  sessionApi: {
    generateTitle: vi.fn().mockResolvedValue({}),
    get: mocks.get,
    getStatus: mocks.status,
    getRuns: mocks.runs,
    getEvents: mocks.events,
    submitChat: vi.fn().mockResolvedValue({
      session_id: "session",
      run_id: "run",
      status: "submitted",
    }),
    markRead: vi.fn().mockResolvedValue(undefined),
    getPendingSteers: vi.fn().mockResolvedValue({ items: [] }),
    getPersistentGoal: vi.fn().mockResolvedValue({ goal: null }),
  },
}));
vi.mock("../../../services/api/session", () => ({
  sessionApi: {
    markRead: vi.fn().mockResolvedValue(undefined),
    getEvents: vi.fn().mockResolvedValue({ events: [] }),
    getScheduledProgress: vi.fn().mockResolvedValue({ progress: [] }),
  },
}));
vi.mock("../../../services/api/authenticatedRequest", () => ({
  authenticatedRequest: vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      agents: [{ id: "fast", name: "Fast" }],
      default_agent: "fast",
      allowed_model_ids: null,
    }),
  }),
}));
vi.mock("../../../services/api/feedback", () => ({
  feedbackApi: { listBySession: vi.fn() },
}));
vi.mock("../../../services/api/tokenManager", () => ({
  getValidAccessToken: vi.fn().mockResolvedValue("token"),
}));
import { useAgent } from "../../useAgent";
import { isSessionRunning } from "../../../components/layout/AppContent/sessionState";

let connections: FetchEventSourceInit[];
const completed = {
  id: "session",
  metadata: { current_run_id: "run", task_status: "completed" },
};
function emit(index: number, event: string, data: object, id = event) {
  connections[index].onmessage?.({
    event,
    data: JSON.stringify({ run_id: "run", ...data }),
    id,
  });
}
beforeEach(() => {
  vi.useFakeTimers();
  connections = [];
  mocks.stream
    .mockReset()
    .mockImplementation(async (_url, config: FetchEventSourceInit) => {
      connections.push(config);
      await config.onopen?.(new Response(null, { status: 200 }));
      await new Promise<void>(
        (resolve) => config.signal?.addEventListener("abort", () => resolve()),
      );
    });
  mocks.get.mockReset().mockResolvedValue(completed);
  mocks.status.mockReset().mockResolvedValue({ status: "running" });
  mocks.runs.mockReset().mockResolvedValue({
    runs: [{ run_id: "run", recommend_questions: ["Next question?"] }],
  });
  mocks.events.mockReset().mockResolvedValue({
    events: [
      {
        id: "stored-user",
        event_type: "user:message",
        run_id: "run",
        data: { content: "hello" },
      },
      {
        id: "stored-answer",
        event_type: "message:chunk",
        run_id: "run",
        data: { content: "Full answer" },
      },
      { id: "stored-done", event_type: "done", run_id: "run", data: {} },
    ],
  });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
async function start() {
  const hook = renderHook(() => useAgent());
  await act(async () => {});
  await act(async () => {
    void hook.result.current.sendMessage("hello");
  });
  expect(connections).toHaveLength(1);
  await act(async () => {
    emit(0, "message:chunk", { content: "Answer" });
  });
  return hook;
}
test("done releases the composer without waiting for a suspended transport to close", async () => {
  const { result } = await start();
  expect(result.current.isLoading).toBe(true);
  await act(async () => {
    emit(0, "done", {});
  });
  expect(result.current.isLoading).toBe(false);
  expect(result.current.messages.at(-1)?.isStreaming).toBe(false);
});
test("a completed conversation stays idle while foreground history synchronization is pending", async () => {
  const { result } = await start();
  await act(async () => {
    emit(0, "done", {});
  });
  expect(
    isSessionRunning(result.current.messages, result.current.isLoading),
  ).toBe(false);
  let finishSync!: (value: typeof completed) => void;
  mocks.get.mockReturnValueOnce(
    new Promise((resolve) => {
      finishSync = resolve;
    }),
  );
  await act(async () => {
    document.dispatchEvent(new Event("resume"));
  });
  expect(result.current.isLoadingHistory).toBe(true);
  expect(result.current.messages.at(-1)?.content).toBe("Answer");
  expect(
    isSessionRunning(result.current.messages, result.current.isLoading),
  ).toBe(false);
  await act(async () => {
    finishSync(completed);
  });
  expect(
    isSessionRunning(result.current.messages, result.current.isLoading),
  ).toBe(false);
  expect(result.current.messages.at(-1)?.content).toBe("Full answer");
});
test("after reconnect, missed recommendations arrive without refreshing the conversation", async () => {
  const { result } = await start();
  mocks.get.mockResolvedValue({
    ...completed,
    metadata: { current_run_id: "run", task_status: "running" },
  });
  mocks.events.mockResolvedValue({
    stream_run_id: "run",
    events: [
      {
        id: "stored-user",
        event_type: "user:message",
        run_id: "run",
        data: { content: "hello" },
      },
    ],
  });
  await act(async () => {
    document.dispatchEvent(new Event("resume"));
  });
  expect(connections).toHaveLength(2);
  mocks.get.mockResolvedValue(completed);
  await act(async () => {
    emit(1, "message:chunk", { content: "Full answer" });
    emit(1, "done", {});
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });
  expect(result.current.messages.at(-1)?.isStreaming).toBe(false);
  expect(result.current.messages.at(-1)?.parts).toContainEqual(
    expect.objectContaining({
      type: "recommend_questions",
      questions: [{ content: "Next question?" }],
    }),
  );
  expect(mocks.events).toHaveBeenCalledTimes(1);
});
test("resume supersedes a status request stranded before suspension", async () => {
  const { result } = await start();
  let finishOld!: (value: { status: string }) => void;
  mocks.status
    .mockReturnValueOnce(
      new Promise((resolve) => {
        finishOld = resolve;
      }),
    )
    .mockResolvedValue({ status: "completed" });
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await act(async () => {
    document.dispatchEvent(new Event("resume"));
  });
  expect(mocks.status).toHaveBeenCalledTimes(1);
  expect(mocks.status.mock.calls[0][2].signal.aborted).toBe(true);
  expect(result.current.isLoading).toBe(false);
  expect(result.current.messages.at(-1)?.content).toBe("Full answer");
  await act(async () => {
    finishOld({ status: "running" });
  });
  expect(result.current.messages.at(-1)?.isStreaming).toBe(false);
  expect(connections).toHaveLength(1);
});

test("watchdog replaces a hung probe even when no resume event is delivered", async () => {
  const { result } = await start();
  mocks.status
    .mockReturnValueOnce(new Promise(() => {}))
    .mockResolvedValue({ status: "completed" });
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(15_000);
  });
  expect(result.current.isLoading).toBe(false);
  expect(result.current.messages.at(-1)?.content).toBe("Full answer");
});

test("recommendation catch-up retries until saved, then stops fetching", async () => {
  const { result } = await start();
  mocks.runs.mockResolvedValueOnce({
    runs: [{ run_id: "run", recommend_questions: [] }],
  });
  await act(async () => {
    emit(0, "done", {});
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });
  expect(
    result.current.messages
      .at(-1)
      ?.parts?.some((part) => part.type === "recommend_questions"),
  ).toBe(false);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });
  expect(
    result.current.messages
      .at(-1)
      ?.parts?.some((part) => part.type === "recommend_questions"),
  ).toBe(true);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_000);
  });
  expect(mocks.runs).toHaveBeenCalledTimes(2);
});

test("a delayed recommendation response cannot modify a different conversation", async () => {
  const { result } = await start();
  let finish!: (value: unknown) => void;
  mocks.runs.mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  await act(async () => {
    emit(0, "done", {});
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });
  await act(async () => {
    result.current.clearMessages();
  });
  await act(async () => {
    finish({
      runs: [{ run_id: "run", recommend_questions: ["Old question"] }],
    });
  });
  expect(result.current.messages).toEqual([]);
});

test("late events after done cannot reopen the completed assistant bubble", async () => {
  const { result } = await start();
  await act(async () => {
    emit(0, "done", {});
  });
  await act(async () => {
    emit(0, "user:message", { content: "hello" }, "late-user");
  });
  expect(result.current.isLoading).toBe(false);
  expect(result.current.messages.at(-1)?.isStreaming).toBe(false);
  expect(result.current.messages.at(-1)?.content).toBe("Answer");
});

test("opening the current run explicitly still catches up recommendations", async () => {
  const { result } = await start();
  await act(async () => {
    emit(0, "done", {});
  });
  await act(async () => {
    await result.current.loadHistory("session", "run");
  });
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });
  expect(
    result.current.messages.find(
      (message) => message.role === "assistant" && message.runId === "run",
    )?.parts,
  ).toContainEqual(
    expect.objectContaining({
      type: "recommend_questions",
      questions: [{ content: "Next question?" }],
    }),
  );
});

test("returning from background reloads the same completed run even if both transports missed its final content", async () => {
  const { result } = await start();
  await act(async () => emit(0, "done", {}));
  await act(async () => document.dispatchEvent(new Event("pause")));
  await act(async () => document.dispatchEvent(new Event("resume")));
  expect(result.current.messages.at(-1)?.content).toBe("Full answer");
  expect(result.current.isLoading).toBe(false);
  expect(mocks.events).toHaveBeenCalled();
});

test("foreground recovery replaces history loading stranded in the background", async () => {
  const { result } = await start();
  mocks.events.mockReturnValueOnce(new Promise(() => {}));
  await act(async () => {
    void result.current.loadHistory("session");
  });
  expect(result.current.isLoadingHistory).toBe(true);
  const oldSignal = mocks.events.mock.calls[0][1].signal;
  await act(async () => document.dispatchEvent(new Event("resume")));
  expect(oldSignal.aborted).toBe(true);
  expect(result.current.isLoadingHistory).toBe(false);
  expect(result.current.messages.at(-1)?.content).toBe("Full answer");
});

test("visibility alone recovers missed updates and ignores a late old SSE frame", async () => {
  const { result } = await start();
  const visibility = vi.spyOn(document, "visibilityState", "get");
  try {
    visibility.mockReturnValue("hidden");
    act(() => document.dispatchEvent(new Event("visibilitychange")));
    visibility.mockReturnValue("visible");
    await act(async () =>
      document.dispatchEvent(new Event("visibilitychange")),
    );
    expect(result.current.messages.at(-1)?.content).toBe("Full answer");
    await act(async () =>
      emit(0, "message:chunk", { content: "Stale" }, "stale"),
    );
    expect(result.current.messages.at(-1)?.content).toBe("Full answer");
  } finally {
    visibility.mockRestore();
  }
});

test("a hung foreground history refresh is replaced by the watchdog", async () => {
  const { result } = await start();
  mocks.events.mockReturnValueOnce(new Promise(() => {}));
  await act(async () => document.dispatchEvent(new Event("resume")));
  const oldSignal = mocks.events.mock.calls[0][1].signal;
  await act(async () => {
    await vi.advanceTimersByTimeAsync(15_000);
  });
  expect(oldSignal.aborted).toBe(true);
  expect(result.current.isLoadingHistory).toBe(false);
  expect(result.current.messages.at(-1)?.content).toBe("Full answer");
});

test("native resume retries recovery even while WebView visibility remains hidden", async () => {
  const { result } = await start();
  const visibility = vi
    .spyOn(document, "visibilityState", "get")
    .mockReturnValue("hidden");
  try {
    mocks.events.mockReturnValueOnce(new Promise(() => {}));
    await act(async () => document.dispatchEvent(new Event("resume")));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(result.current.isLoadingHistory).toBe(false);
    expect(result.current.messages.at(-1)?.content).toBe("Full answer");
  } finally {
    visibility.mockRestore();
  }
});
