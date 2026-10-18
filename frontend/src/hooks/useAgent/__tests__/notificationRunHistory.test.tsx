/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  events: vi.fn(),
  connect: vi.fn(),
  goal: vi.fn(),
  steers: vi.fn(),
  submit: vi.fn(),
  streamMarkRead: vi.fn(),
  userId: "user-a",
}));
vi.mock("../../useAuth", () => ({
  useAuth: () => ({
    hasAnyPermission: () => false,
    user: { id: mocks.userId },
  }),
}));
vi.mock("../../../services/api", () => ({
  sessionApi: {
    get: mocks.get,
    getEvents: mocks.events,
    submitChat: mocks.submit,
    markRead: vi.fn().mockResolvedValue(undefined),
    getPendingSteers: mocks.steers,
    getPersistentGoal: mocks.goal,
  },
}));
vi.mock("../../../services/api/session", () => ({
  sessionApi: { markRead: mocks.streamMarkRead },
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
vi.mock("../sseConnection", async () => ({
  ...(await vi.importActual<typeof import("../sseConnection")>(
    "../sseConnection",
  )),
  connectToSSE: mocks.connect,
}));
import { useAgent } from "../../useAgent";
import { handleStreamEvent, type EventHandlerContext } from "../eventHandlers";
import type { StreamEvent, HistoryEvent } from "../types";
import {
  reconstructMessagesFromEvents,
  prepareMessagesForRunningRun,
} from "../historyLoader";
import * as historyFetch from "../../../services/api/fetch";
import {
  SCHEDULED_PROGRESS_EVENT,
  SCHEDULED_RESULT_EVENT,
} from "../scheduledResults";

function events(run: string, timestamp: string) {
  return [
    {
      id: `${run}-user`,
      event_type: "user:message",
      run_id: run,
      timestamp,
      data: { content: `question-${run}` },
    },
    {
      id: `${run}-answer`,
      event_type: "message:chunk",
      run_id: run,
      timestamp,
      data: { content: `answer-${run}` },
    },
  ];
}
const latestWindow = () => ({
  events: events("new-run", "2026-10-13T10:00:00Z"),
  stream_run_id: "new-run",
  has_more_traces: true,
  trace_window: {
    oldest_trace_started_at: "2026-10-13T10:00:00Z",
    oldest_trace_id: "new-trace",
  },
});
let liveController: AbortController;
beforeEach(() => {
  mocks.userId = "user-a";
  mocks.streamMarkRead.mockReset().mockResolvedValue(undefined);
  mocks.submit.mockReset().mockResolvedValue({
    session_id: "C",
    run_id: "sent-run",
    trace_id: "sent-trace",
    status: "submitted",
  });
  mocks.steers.mockReset().mockResolvedValue({ items: [] });
  mocks.goal.mockReset().mockResolvedValue({ goal: null });
  mocks.get.mockReset().mockImplementation(async (id: string) => ({
    id,
    metadata: { current_run_id: "new-run", task_status: "running" },
  }));
  mocks.events
    .mockReset()
    .mockImplementation(async (_id: string, options: { run_id?: string }) =>
      options.run_id
        ? { events: events(options.run_id, "2026-10-01T10:00:00Z") }
        : latestWindow(),
    );
  mocks.connect
    .mockReset()
    .mockImplementation(
      async (
        _session: string,
        _run: string,
        _message: string,
        ctx: { abortControllerRef: { current: AbortController | null } },
      ) => {
        liveController = new AbortController();
        ctx.abortControllerRef.current = liveController;
      },
    );
});

function deliverScheduledResult(sessionId: string, id = "late-result") {
  window.dispatchEvent(
    new CustomEvent(SCHEDULED_RESULT_EVENT, {
      detail: {
        session_id: sessionId,
        run_id: id,
        message_id: id,
        task_id: "schedule-task",
        task_name: "Schedule",
        content: id,
        timestamp: "2026-10-13T10:01:00Z",
      },
    }),
  );
}

test.each([false, true])(
  "opening a scheduled result keeps the current human stream (result in first page: %s)",
  async (inFirstPage) => {
    const scheduled = {
      id: "scheduled-event",
      run_id: "scheduled-old",
      event_type: "scheduled:result",
      timestamp: "2026-10-01T10:00:00Z",
      data: {
        session_id: "C",
        run_id: "scheduled-old",
        message_id: "scheduled-result:scheduled-old",
        task_id: "task",
        task_name: "Task",
        content: "result",
        timestamp: "2026-10-01T10:00:00Z",
      },
    };
    mocks.events.mockImplementation(
      async (_id: string, options: { run_id?: string }) =>
        options.run_id
          ? { events: [scheduled] }
          : {
              ...latestWindow(),
              events: [
                ...latestWindow().events,
                ...(inFirstPage ? [scheduled] : []),
              ],
            },
    );
    const { result } = renderHook(() => useAgent());
    await act(async () => {
      await result.current.loadHistory("C", "scheduled-old");
    });
    expect(result.current.currentRunId).toBe("new-run");
    expect(mocks.connect).toHaveBeenCalledOnce();
    expect(mocks.connect.mock.calls[0].slice(0, 2)).toEqual(["C", "new-run"]);
    expect(
      result.current.messages.some(
        (message) => message.id === "scheduled-result:scheduled-old",
      ),
    ).toBe(true);
  },
);

test("same-session history replacement retains a scheduled result delivered after its request snapshot", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("C");
  });
  let finish!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.loadHistory("C");
  });
  act(() => deliverScheduledResult("C"));
  await act(async () => {
    finish(latestWindow());
    await pending;
  });
  expect(result.current.messages.map((message) => message.content)).toEqual([
    "question-new-run",
    "answer-new-run",
    "late-result",
  ]);
  expect(
    result.current.messages.filter((message) => message.id === "late-result"),
  ).toHaveLength(1);
});

test("send takeover restores the original history together with a late scheduled result", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("C");
  });
  let finish!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.loadHistory("C");
  });
  act(() => deliverScheduledResult("C"));
  await act(async () => {
    await result.current.sendMessage("next question");
  });
  await act(async () => {
    finish(latestWindow());
    await pending;
  });
  expect(result.current.messages.map((message) => message.content)).toEqual(
    expect.arrayContaining([
      "question-new-run",
      "answer-new-run",
      "late-result",
      "next question",
    ]),
  );
  expect(
    result.current.messages.filter((message) => message.id === "late-result"),
  ).toHaveLength(1);
});

test.each([false, true])(
  "a quiet scheduled run cannot return from a history snapshot (send takeover: %s)",
  async (takeover) => {
    const { result } = renderHook(() => useAgent());
    await act(async () => {
      await result.current.loadHistory("C");
    });
    const progress = {
      session_id: "C",
      run_id: "scheduled-run",
      message_id: "scheduled-result:scheduled-run",
      task_id: "task",
      task_name: "Quiet task",
      content: "",
      timestamp: "2026-10-13T10:01:00Z",
    };
    act(() =>
      window.dispatchEvent(
        new CustomEvent(SCHEDULED_PROGRESS_EVENT, {
          detail: {
            ...progress,
            status: "running",
            updated_at: "2026-10-13T10:01:01Z",
          },
        }),
      ),
    );
    expect(
      result.current.messages.some(
        (message) => message.id === progress.message_id,
      ),
    ).toBe(true);
    let finish!: (value: ReturnType<typeof latestWindow>) => void;
    mocks.events.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    let pending!: Promise<unknown>;
    act(() => {
      pending = result.current.loadHistory("C");
    });
    act(() =>
      window.dispatchEvent(
        new CustomEvent(SCHEDULED_PROGRESS_EVENT, {
          detail: {
            ...progress,
            status: "quiet",
            updated_at: "2026-10-13T10:01:02Z",
          },
        }),
      ),
    );
    if (takeover)
      await act(async () => {
        await result.current.sendMessage("next question");
      });
    await act(async () => {
      finish(latestWindow());
      await pending;
    });
    expect(
      result.current.messages.some(
        (message) => message.id === progress.message_id,
      ),
    ).toBe(false);
    expect(
      result.current.messages.some(
        (message) => message.content === "answer-new-run",
      ),
    ).toBe(true);
  },
);

test("a scheduled result from A cannot be merged into a later B history load", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("A");
  });
  act(() => deliverScheduledResult("A"));
  await act(async () => {
    await result.current.loadHistory("B");
  });
  expect(
    result.current.messages.some(
      (message) => message.metadata?.scheduledTaskId,
    ),
  ).toBe(false);
});

test("changing accounts invalidates pending history and its late scheduled results", async () => {
  const { result, rerender } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("A");
  });
  let finish!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.loadHistory("A");
  });
  act(() => deliverScheduledResult("A"));
  mocks.userId = "user-b";
  rerender();
  await act(async () => {
    finish(latestWindow());
    await pending;
  });
  expect(result.current.sessionId).toBeNull();
  expect(result.current.messages).toEqual([]);
});

test("complete history is visible while optional steers and goal are pending without reconnecting early", async () => {
  let resolveSteers!: (value: { items: [] }) => void;
  let resolveGoal!: (value: { goal: null }) => void;
  mocks.steers.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveSteers = resolve;
      }),
  );
  mocks.goal.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveGoal = resolve;
      }),
  );
  const { result } = renderHook(() => useAgent());
  let loading!: Promise<unknown>;
  act(() => {
    loading = result.current.loadHistory("s1");
  });
  await waitFor(() =>
    expect(result.current.messages.map((message) => message.content)).toEqual([
      "question-new-run",
      "answer-new-run",
    ]),
  );
  expect(result.current.hasMoreHistoryTraces).toBe(true);
  expect(result.current.isLoadingHistory).toBe(true);
  expect(mocks.connect).not.toHaveBeenCalled();
  await act(async () => {
    resolveSteers({ items: [] });
    resolveGoal({ goal: null });
    await loading;
  });
  expect(result.current.isLoadingHistory).toBe(false);
  expect(mocks.connect).toHaveBeenCalledOnce();
});

test("an old optional response cannot overwrite a newer session after primary history was displayed", async () => {
  let resolveSteers!: (value: { items: [] }) => void;
  mocks.steers.mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        resolveSteers = resolve;
      }),
  );
  const { result } = renderHook(() => useAgent());
  let oldLoad!: Promise<unknown>;
  act(() => {
    oldLoad = result.current.loadHistory("s1");
  });
  await waitFor(() => expect(result.current.messages).toHaveLength(2));
  mocks.events.mockImplementationOnce(async () => ({
    events: events("other-run", "2026-10-15T10:00:00Z"),
  }));
  await act(async () => {
    await result.current.loadHistory("s2");
  });
  await act(async () => {
    resolveSteers({ items: [] });
    await oldLoad;
  });
  expect(result.current.sessionId).toBe("s2");
  expect(result.current.messages.map((message) => message.runId)).toEqual([
    "other-run",
    "other-run",
  ]);
  expect(mocks.connect).not.toHaveBeenCalled();
});

test("switching starts pending steers and goal reads alongside the full history window", async () => {
  let resolveEvents!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolveEvents = done;
      }),
  );
  const { result } = renderHook(() => useAgent());
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.loadHistory("s1");
  });
  try {
    await waitFor(() => {
      expect(mocks.steers).toHaveBeenCalledWith(
        "s1",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
      expect(mocks.goal).toHaveBeenCalledWith(
        "s1",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });
  } finally {
    await act(async () => {
      resolveEvents(latestWindow());
      await pending;
    });
  }
  expect(
    result.current.messages.some(
      (message) => message.content === "question-new-run",
    ),
  ).toBe(true);
  expect(
    result.current.messages.some(
      (message) => message.content === "answer-new-run",
    ),
  ).toBe(true);
  expect(result.current.hasMoreHistoryTraces).toBe(true);
});

test("initial old-run deep link reads the exact run once alongside the recent window", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("s1", "old-run");
  });
  expect(mocks.events).toHaveBeenCalledWith(
    "s1",
    expect.objectContaining({
      run_id: "old-run",
      compact_message_chunks: true,
    }),
  );
  expect(mocks.events).toHaveBeenCalledTimes(2);
  expect(
    result.current.messages.some((message) => message.runId === "old-run"),
  ).toBe(true);
  expect(
    result.current.messages.some((message) => message.runId === "new-run"),
  ).toBe(true);
  expect(result.current.hasMoreHistoryTraces).toBe(true);
});

test("same-session missing notification run is merged without aborting the live run or resetting its pagination", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("s1");
  });
  await waitFor(() => expect(mocks.connect).toHaveBeenCalledOnce());
  const originalController = liveController;
  mocks.events.mockClear();
  mocks.get.mockClear();
  await act(async () => {
    await result.current.loadHistory("s1", "old-run");
  });
  expect(mocks.events).toHaveBeenCalledTimes(1);
  expect(mocks.events).toHaveBeenCalledWith(
    "s1",
    expect.objectContaining({ run_id: "old-run" }),
  );
  expect(mocks.get).not.toHaveBeenCalled();
  expect(originalController.signal.aborted).toBe(false);
  expect(mocks.connect).toHaveBeenCalledOnce();
  expect(
    result.current.messages.some((message) => message.runId === "old-run"),
  ).toBe(true);
  expect(
    result.current.messages.find(
      (message) => message.role === "assistant" && message.runId === "new-run",
    )?.isStreaming,
  ).toBe(true);
  expect(result.current.hasMoreHistoryTraces).toBe(true);
});

test("same-session notification for an already loaded run does not refetch or reconnect", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("s1");
  });
  const originalController = liveController;
  mocks.events.mockClear();
  mocks.get.mockClear();
  await act(async () => {
    await result.current.loadHistory("s1", "new-run");
  });
  expect(mocks.events).not.toHaveBeenCalled();
  expect(mocks.get).not.toHaveBeenCalled();
  expect(originalController.signal.aborted).toBe(false);
  expect(mocks.connect).toHaveBeenCalledOnce();
});

test("Goal polling that discovers a new admitted run still restores its current SSE owner", async () => {
  const goal = {
    id: "g1",
    session_id: "s1",
    user_id: "u1",
    status: "active",
    objective: "task",
    rubric: "verified",
    revision: 1,
    version: 1,
    current_run_id: "new-run",
  };
  mocks.goal.mockResolvedValueOnce({ goal }).mockResolvedValue({
    goal: { ...goal, revision: 2, current_run_id: "goal-run" },
  });
  mocks.get
    .mockResolvedValueOnce({
      id: "s1",
      metadata: { current_run_id: "new-run" },
    })
    .mockResolvedValue({ id: "s1", metadata: { current_run_id: "goal-run" } });
  mocks.events.mockResolvedValueOnce(latestWindow()).mockResolvedValue({
    ...latestWindow(),
    events: events("goal-run", "2026-10-13T11:00:00Z"),
    stream_run_id: "goal-run",
  });
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("s1");
  });
  await waitFor(() => expect(mocks.connect).toHaveBeenCalledTimes(2));
  expect(mocks.connect.mock.calls[1][1]).toBe("goal-run");
});

test("late exact-run reply after changing sessions cannot insert the previous session's target", async () => {
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("s1");
  });
  let resolve!: (value: { events: ReturnType<typeof events> }) => void;
  mocks.events.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  let pending!: Promise<unknown>;
  act(() => {
    pending = result.current.loadHistory("s1", "old-run");
  });
  await act(async () => {
    await result.current.loadHistory("s2");
  });
  await act(async () => {
    resolve({ events: events("old-run", "2026-10-01T10:00:00Z") });
    await pending;
  });
  expect(result.current.sessionId).toBe("s2");
  expect(
    result.current.messages.some((message) => message.runId === "old-run"),
  ).toBe(false);
});

test("history pages prefetch approval metadata and retain previous-page statuses without per-approval reads", async () => {
  const lookup = vi.spyOn(historyFetch, "authFetch").mockResolvedValue(null);
  const approval = (run: string) => ({
    event_type: "approval_required",
    run_id: run,
    timestamp:
      run === "old-run" ? "2026-10-01T10:00:00Z" : "2026-10-13T10:00:00Z",
    data: { id: `approval-${run}`, message: "confirm" },
  });
  const status = (run: string) => ({
    id: `approval-${run}`,
    status: "approved",
    metadata: { approval_type: "scheduled_task_create" },
  });
  mocks.events.mockImplementation(
    async (_id: string, options: { before_trace_id?: string }) =>
      options.before_trace_id
        ? {
            events: [
              ...events("old-run", "2026-10-01T10:00:00Z"),
              approval("old-run"),
            ],
            approval_statuses: { "approval-old-run": status("old-run") },
            has_more_traces: false,
            trace_window: null,
          }
        : {
            ...latestWindow(),
            events: [...latestWindow().events, approval("new-run")],
            approval_statuses: { "approval-new-run": status("new-run") },
          },
  );
  try {
    const { result } = renderHook(() => useAgent());
    await act(async () => {
      await result.current.loadHistory("s1");
    });
    await act(async () => {
      await result.current.loadOlderHistory();
    });
    expect(mocks.events).toHaveBeenCalledTimes(2);
    for (const call of mocks.events.mock.calls)
      expect(call[1]).toEqual(
        expect.objectContaining({ include_approval_statuses: true }),
      );
    expect(lookup).not.toHaveBeenCalled();
    for (const run of ["new-run", "old-run"]) {
      expect(
        result.current.messages.some(
          (message) => message.content === `question-${run}`,
        ),
      ).toBe(true);
      const assistant = result.current.messages.find(
        (message) => message.role === "assistant" && message.runId === run,
      );
      expect(
        assistant?.parts?.find(
          (part) => part.type === "tool" && part.id === `approval-${run}`,
        ),
      ).toMatchObject({ isPending: false, success: true });
    }
  } finally {
    lookup.mockRestore();
  }
});

test("a same-session notification during optional hydration retains the current run SSE owner", async () => {
  let resolveMainSteers!: (value: {
    items: { message_id: string; content: string; created_at: string }[];
  }) => void;
  let resolveMainGoal!: (value: {
    goal: { id: string; session_id: string; revision: number };
  }) => void;
  let resolveNotificationSteers!: (value: { items: [] }) => void;
  const mainSteers = new Promise((resolve) => {
    resolveMainSteers = resolve;
  });
  const mainGoal = new Promise((resolve) => {
    resolveMainGoal = resolve;
  });
  const notificationSteers = new Promise((resolve) => {
    resolveNotificationSteers = resolve;
  });
  mocks.steers
    .mockReturnValueOnce(mainSteers)
    .mockReturnValueOnce(notificationSteers);
  mocks.goal.mockReturnValueOnce(mainGoal);
  const { result } = renderHook(() => useAgent());
  let initialLoad!: Promise<unknown>;
  act(() => {
    initialLoad = result.current.loadHistory("s1");
  });
  await waitFor(() => {
    expect(result.current.sessionId).toBe("s1");
    expect(result.current.messages.map((message) => message.content)).toEqual([
      "question-new-run",
      "answer-new-run",
    ]);
  });
  const initialSignal = mocks.events.mock.calls[0][1].signal as AbortSignal;
  expect(result.current.isLoadingHistory).toBe(true);
  expect(mocks.connect).not.toHaveBeenCalled();
  let notificationLoad!: Promise<unknown>;
  act(() => {
    notificationLoad = result.current.loadHistory("s1", "old-run");
  });
  try {
    await waitFor(() => {
      expect(
        result.current.messages.some((message) => message.runId === "old-run"),
      ).toBe(true);
      expect(
        result.current.messages.some((message) => message.runId === "new-run"),
      ).toBe(true);
    });
    expect(initialSignal.aborted).toBe(true);
    expect(mocks.connect).not.toHaveBeenCalled();
    await act(async () => {
      resolveNotificationSteers({ items: [] });
      await notificationLoad;
    });
    expect(mocks.connect).toHaveBeenCalledOnce();
    expect(mocks.connect.mock.calls[0].slice(0, 2)).toEqual(["s1", "new-run"]);
    expect(result.current.currentRunId).toBe("new-run");
    expect(result.current.isLoadingHistory).toBe(false);
    expect(result.current.hasMoreHistoryTraces).toBe(true);
    expect(mocks.get).toHaveBeenCalledTimes(2);
    mocks.events.mockImplementationOnce(async () => ({
      events: events("page-run", "2026-09-01T10:00:00Z"),
      has_more_traces: false,
      trace_window: null,
    }));
    await act(async () => {
      await result.current.loadOlderHistory();
    });
    expect(mocks.events).toHaveBeenLastCalledWith(
      "s1",
      expect.objectContaining({
        before_trace_id: "new-trace",
        before_trace_started_at: "2026-10-13T10:00:00Z",
      }),
    );
    for (const run of ["page-run", "old-run", "new-run"]) {
      expect(
        result.current.messages.some(
          (message) => message.content === `question-${run}`,
        ),
      ).toBe(true);
      expect(
        result.current.messages.some(
          (message) => message.content === `answer-${run}`,
        ),
      ).toBe(true);
    }
  } finally {
    await act(async () => {
      resolveMainSteers({
        items: [
          {
            message_id: "obsolete-steer",
            content: "obsolete queue",
            created_at: "2026-10-01T10:00:00Z",
          },
        ],
      });
      resolveMainGoal({
        goal: { id: "obsolete-goal", session_id: "s1", revision: 99 },
      });
      await initialLoad;
    });
  }
  expect(mocks.connect).toHaveBeenCalledOnce();
  expect(
    result.current.steerMessages.some((item) => item.id === "obsolete-steer"),
  ).toBe(false);
  expect(result.current.persistentGoal).toBeNull();
});

test.each(["success", "abort"] as const)(
  "stale %s history response cannot restore C while the next session is pending",
  async (outcome) => {
    type Window = { events: ReturnType<typeof events> };
    let resolveA!: (value: Window) => void;
    let rejectA!: (reason: Error) => void;
    let resolveB!: (value: Window) => void;
    mocks.events.mockImplementation(async (id: string) => {
      if (id === "A")
        return new Promise<Window>((resolve, reject) => {
          resolveA = resolve;
          rejectA = reject;
        });
      if (id === "B")
        return new Promise<Window>((resolve) => {
          resolveB = resolve;
        });
      return { events: events("C-run", "2026-10-13T10:00:00Z") };
    });
    const { result } = renderHook(() => useAgent());
    await act(async () => {
      await result.current.loadHistory("C");
    });
    expect(result.current.messages.map((message) => message.content)).toEqual([
      "question-C-run",
      "answer-C-run",
    ]);
    let loadA!: Promise<unknown>;
    let loadB!: Promise<unknown>;
    act(() => {
      loadA = result.current.loadHistory("A");
    });
    await waitFor(() => expect(result.current.messages).toEqual([]));
    act(() => {
      loadB = result.current.loadHistory("B");
    });
    try {
      await act(async () => {
        if (outcome === "abort")
          rejectA(
            Object.assign(new Error("cancelled A"), { name: "AbortError" }),
          );
        else resolveA({ events: events("A-run", "2026-10-14T10:00:00Z") });
        await loadA;
      });
      expect(result.current.messages).toEqual([]);
      expect(result.current.isLoadingHistory).toBe(true);
      expect(result.current.steerMessages).toEqual([]);
      expect(mocks.connect).not.toHaveBeenCalled();
    } finally {
      await act(async () => {
        resolveB({ events: events("B-run", "2026-10-15T10:00:00Z") });
        await loadB;
      });
    }
    expect(result.current.sessionId).toBe("B");
    expect(result.current.messages.map((message) => message.content)).toEqual([
      "question-B-run",
      "answer-B-run",
    ]);
  },
);

test.each(["success", "abort"] as const)(
  "stale %s history response cannot revive C after clearing the session",
  async (outcome) => {
    type Window = { events: ReturnType<typeof events> };
    let resolveA!: (value: Window) => void;
    let rejectA!: (reason: Error) => void;
    mocks.events.mockImplementation(async (id: string) =>
      id === "A"
        ? new Promise<Window>((resolve, reject) => {
            resolveA = resolve;
            rejectA = reject;
          })
        : { events: events("C-run", "2026-10-13T10:00:00Z") },
    );
    const { result } = renderHook(() => useAgent());
    await act(async () => {
      await result.current.loadHistory("C");
    });
    expect(result.current.messages).toHaveLength(2);
    let loadA!: Promise<unknown>;
    act(() => {
      loadA = result.current.loadHistory("A");
    });
    await waitFor(() => expect(result.current.messages).toEqual([]));
    act(() => {
      result.current.clearMessages();
    });
    await act(async () => {
      if (outcome === "abort")
        rejectA(
          Object.assign(new Error("cancelled A"), { name: "AbortError" }),
        );
      else resolveA({ events: events("A-run", "2026-10-14T10:00:00Z") });
      await loadA;
    });
    expect(result.current.sessionId).toBeNull();
    expect(result.current.messages).toEqual([]);
    expect(result.current.currentRunId).toBeNull();
    expect(result.current.steerMessages).toEqual([]);
    expect(result.current.persistentGoal).toBeNull();
    expect(result.current.isLoadingHistory).toBe(false);
    expect(mocks.connect).not.toHaveBeenCalled();
  },
);

test("sending during a same-session refresh retains its previous history and ignores the aborted refresh", async () => {
  type Window = { events: ReturnType<typeof events> };
  let rejectRefresh!: (reason: Error) => void;
  mocks.events
    .mockResolvedValueOnce({ events: events("C-run", "2026-10-13T10:00:00Z") })
    .mockImplementationOnce(
      () =>
        new Promise<Window>((_resolve, reject) => {
          rejectRefresh = reject;
        }),
    );
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("C");
  });
  let refresh!: Promise<unknown>;
  act(() => {
    refresh = result.current.loadHistory("C");
  });
  await waitFor(() => expect(result.current.messages).toEqual([]));
  await act(async () => {
    await result.current.sendMessage("next question");
  });
  await act(async () => {
    rejectRefresh(
      Object.assign(new Error("send takeover"), { name: "AbortError" }),
    );
    await refresh;
  });
  expect(mocks.submit.mock.calls[0].slice(0, 3)).toEqual([
    expect.any(String),
    "next question",
    "C",
  ]);
  expect(result.current.sessionId).toBe("C");
  expect(result.current.messages.map((message) => message.content)).toEqual(
    expect.arrayContaining(["question-C-run", "answer-C-run", "next question"]),
  );
  expect(result.current.currentRunId).toBe("sent-run");
  expect(result.current.isLoadingHistory).toBe(false);
  expect(mocks.connect).toHaveBeenCalledOnce();
  expect(mocks.connect.mock.calls[0].slice(0, 2)).toEqual(["C", "sent-run"]);
});

test.each(["next question", "/goal clear"])(
  "repeated same-session refreshes retain history when %s takes ownership",
  async (content) => {
    type Window = { events: ReturnType<typeof events> };
    let rejectFirst!: (reason: Error) => void;
    let rejectSecond!: (reason: Error) => void;
    mocks.events
      .mockResolvedValueOnce({
        events: events("C-run", "2026-10-13T10:00:00Z"),
      })
      .mockImplementationOnce(
        () =>
          new Promise<Window>((_resolve, reject) => {
            rejectFirst = reject;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise<Window>((_resolve, reject) => {
            rejectSecond = reject;
          }),
      );
    const { result } = renderHook(() => useAgent());
    await act(async () => {
      await result.current.loadHistory("C");
    });
    expect(result.current.messages.map((message) => message.content)).toEqual([
      "question-C-run",
      "answer-C-run",
    ]);
    let first!: Promise<unknown>;
    let second!: Promise<unknown>;
    act(() => {
      first = result.current.loadHistory("C");
    });
    await waitFor(() => expect(result.current.messages).toEqual([]));
    act(() => {
      second = result.current.loadHistory("C");
    });
    // An obsolete finally must not clear the replacement refresh's snapshot.
    await act(async () => {
      rejectFirst(
        Object.assign(new Error("second refresh"), { name: "AbortError" }),
      );
      await first;
    });
    await act(async () => {
      await result.current.sendMessage(content);
    });
    await act(async () => {
      rejectSecond(
        Object.assign(new Error("send takeover"), { name: "AbortError" }),
      );
      await second;
    });
    expect(result.current.sessionId).toBe("C");
    expect(result.current.messages.map((message) => message.content)).toEqual(
      expect.arrayContaining(["question-C-run", "answer-C-run"]),
    );
    expect(result.current.isLoadingHistory).toBe(false);
    if (content === "/goal clear") {
      expect(result.current.messages.map((message) => message.content)).toEqual(
        ["question-C-run", "answer-C-run"],
      );
      expect(mocks.submit).not.toHaveBeenCalled();
      expect(mocks.connect).not.toHaveBeenCalled();
    } else {
      expect(
        result.current.messages.some((message) => message.content === content),
      ).toBe(true);
      expect(result.current.currentRunId).toBe("sent-run");
      expect(mocks.submit).toHaveBeenCalledOnce();
      expect(mocks.connect).toHaveBeenCalledOnce();
      expect(mocks.connect.mock.calls[0].slice(0, 2)).toEqual([
        "C",
        "sent-run",
      ]);
    }
  },
);

function emitLiveReply(call: unknown[], run: string, terminal: boolean) {
  const messageId = call[2] as string;
  const context = call[3] as EventHandlerContext;
  const emit = (
    event: StreamEvent["event"],
    data: Record<string, unknown>,
    suffix: string,
  ) =>
    handleStreamEvent(
      { event, data: JSON.stringify({ run_id: run, ...data }) },
      messageId,
      `${run}-${suffix}`,
      "2026-10-16T10:00:00Z",
      context,
    );
  emit("message:chunk", { content: " live text" }, "live-text");
  emit(
    "tool:start",
    { tool: "bash", tool_call_id: "live-tool", args: { cmd: "printf live" } },
    "live-tool-start",
  );
  emit(
    "tool:result",
    {
      tool: "bash",
      tool_call_id: "live-tool",
      result: { output: "live result", attachment: "report.txt" },
      success: true,
    },
    "live-tool-result",
  );
  emit(
    "goal:start",
    { goal: { objective: "live objective", rubric: "live rubric" } },
    "live-goal",
  );
  if (terminal) emit("done", {}, "live-done");
}

test.each([false, true])(
  "older page after a new send preserves its live reply, goal and terminal=%s while advancing the cursor",
  async (terminal) => {
    let resolveOlder!: (value: ReturnType<typeof latestWindow>) => void;
    let finishSend!: () => void;
    mocks.events.mockImplementation(
      async (_id: string, options: { before_trace_id?: string }) => {
        if (options.before_trace_id === "new-trace")
          return new Promise<ReturnType<typeof latestWindow>>((resolve) => {
            resolveOlder = resolve;
          });
        if (options.before_trace_id === "older-trace")
          return { events: [], has_more_traces: false };
        return { ...latestWindow(), stream_run_id: undefined };
      },
    );
    mocks.connect.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finishSend = resolve;
        }),
    );
    const { result } = renderHook(() => useAgent());
    await act(async () => {
      await result.current.loadHistory("C");
    });
    let older!: Promise<void>;
    act(() => {
      older = result.current.loadOlderHistory();
    });
    let sending!: Promise<void>;
    act(() => {
      sending = result.current.sendMessage("next question");
    });
    await waitFor(() => expect(mocks.connect).toHaveBeenCalledOnce());
    await act(async () => {
      emitLiveReply(mocks.connect.mock.calls[0], "sent-run", terminal);
    });
    if (terminal)
      await act(async () => {
        finishSend();
        await sending;
      });
    const liveReply = result.current.messages.find(
      (message) => message.role === "assistant" && message.runId === "sent-run",
    );
    const liveGoal = result.current.goalsByRunId["sent-run"];
    expect(liveReply?.content).toContain("live text");
    expect(
      liveReply?.parts?.find(
        (part) => part.type === "tool" && part.id === "live-tool",
      ),
    ).toMatchObject({
      args: { cmd: "printf live" },
      result: { output: "live result", attachment: "report.txt" },
      success: true,
    });
    expect(liveGoal).toMatchObject({
      objective: "live objective",
      rubric: "live rubric",
    });
    try {
      await act(async () => {
        resolveOlder({
          ...latestWindow(),
          events: events("older-run", "2026-10-01T10:00:00Z"),
          trace_window: {
            oldest_trace_started_at: "2026-10-01T10:00:00Z",
            oldest_trace_id: "older-trace",
          },
        });
        await older;
      });
      expect(
        result.current.messages.find(
          (message) =>
            message.role === "assistant" && message.runId === "sent-run",
        ),
      ).toEqual(liveReply);
      expect(
        result.current.messages.some(
          (message) => message.content === "next question",
        ),
      ).toBe(true);
      expect(result.current.goalsByRunId["sent-run"]).toEqual(liveGoal);
      expect(result.current.messages.map((message) => message.content)).toEqual(
        expect.arrayContaining([
          "question-older-run",
          "answer-older-run",
          "question-new-run",
          "answer-new-run",
        ]),
      );
      await act(async () => {
        await result.current.loadOlderHistory();
      });
      expect(mocks.events.mock.calls.at(-1)?.[1]).toMatchObject({
        before_trace_id: "older-trace",
      });
      if (!terminal) {
        const call = mocks.connect.mock.calls[0];
        await act(async () => {
          handleStreamEvent(
            {
              event: "message:chunk",
              data: JSON.stringify({
                run_id: "sent-run",
                content: "+continued",
                _source_id: "continued",
              }),
            },
            call[2],
            "continued",
            "2026-10-17T00:00:00Z",
            call[3],
          );
        });
        expect(
          result.current.messages.find(
            (message) =>
              message.role === "assistant" && message.runId === "sent-run",
          ),
        ).toMatchObject({
          id: liveReply?.id,
          timestamp: liveReply?.timestamp,
          content: `${liveReply?.content}+continued`,
        });
      }
    } finally {
      if (!terminal)
        await act(async () => {
          finishSend();
          await sending;
        });
    }
  },
);

test.each([false, true])(
  "older page preserves the current SSE text, complete tool payload and terminal=%s",
  async (terminal) => {
    let resolveOlder!: (value: ReturnType<typeof latestWindow>) => void;
    mocks.events.mockImplementation(
      async (_id: string, options: { before_trace_id?: string }) =>
        options.before_trace_id
          ? new Promise<ReturnType<typeof latestWindow>>((resolve) => {
              resolveOlder = resolve;
            })
          : latestWindow(),
    );
    const { result } = renderHook(() => useAgent());
    await act(async () => {
      await result.current.loadHistory("C");
    });
    let older!: Promise<void>;
    act(() => {
      older = result.current.loadOlderHistory();
    });
    await act(async () => {
      emitLiveReply(mocks.connect.mock.calls[0], "new-run", terminal);
    });
    const liveReply = result.current.messages.find(
      (message) => message.role === "assistant" && message.runId === "new-run",
    );
    const liveGoal = result.current.goalsByRunId["new-run"];
    expect(liveReply?.content).toContain("live text");
    expect(
      liveReply?.parts?.find(
        (part) => part.type === "tool" && part.id === "live-tool",
      ),
    ).toMatchObject({
      args: { cmd: "printf live" },
      result: { output: "live result", attachment: "report.txt" },
      success: true,
    });
    expect(liveGoal).toMatchObject({
      objective: "live objective",
      rubric: "live rubric",
    });
    await act(async () => {
      resolveOlder({
        ...latestWindow(),
        events: events("older-run", "2026-10-01T10:00:00Z"),
        has_more_traces: false,
      });
      await older;
    });
    expect(
      result.current.messages.find(
        (message) =>
          message.role === "assistant" && message.runId === "new-run",
      ),
    ).toEqual(liveReply);
    expect(result.current.goalsByRunId["new-run"]).toEqual(liveGoal);
    expect(result.current.messages.map((message) => message.content)).toEqual(
      expect.arrayContaining([
        "question-older-run",
        "answer-older-run",
        "question-new-run",
      ]),
    );
    expect(result.current.hasMoreHistoryTraces).toBe(false);
    expect(mocks.connect).toHaveBeenCalledOnce();
  },
);

test("returning to A before B finishes preserves A history when sending takes over", async () => {
  type Window = { events: ReturnType<typeof events> };
  let rejectB!: (reason: Error) => void;
  let rejectA!: (reason: Error) => void;
  mocks.events
    .mockResolvedValueOnce({ events: events("A-run", "2026-10-13T10:00:00Z") })
    .mockImplementationOnce(
      () =>
        new Promise<Window>((_resolve, reject) => {
          rejectB = reject;
        }),
    )
    .mockImplementationOnce(
      () =>
        new Promise<Window>((_resolve, reject) => {
          rejectA = reject;
        }),
    );
  mocks.submit.mockResolvedValueOnce({
    session_id: "A",
    run_id: "sent-run",
    trace_id: "sent-trace",
    status: "submitted",
  });
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("A");
  });
  let loadB!: Promise<unknown>;
  let loadA!: Promise<unknown>;
  act(() => {
    loadB = result.current.loadHistory("B");
  });
  await waitFor(() => expect(result.current.messages).toEqual([]));
  act(() => {
    loadA = result.current.loadHistory("A");
  });
  await act(async () => {
    rejectB(Object.assign(new Error("return to A"), { name: "AbortError" }));
    await loadB;
  });
  await act(async () => {
    await result.current.sendMessage("next question");
  });
  await act(async () => {
    rejectA(Object.assign(new Error("send takeover"), { name: "AbortError" }));
    await loadA;
  });
  expect(result.current.sessionId).toBe("A");
  expect(result.current.messages.map((message) => message.content)).toEqual(
    expect.arrayContaining(["question-A-run", "answer-A-run", "next question"]),
  );
  expect(mocks.submit.mock.calls[0][2]).toBe("A");
  expect(mocks.connect.mock.calls[0].slice(0, 2)).toEqual(["A", "sent-run"]);
});

test.each([false, true])(
  "same-assistant older retry plus live events equals complete replay with terminal=%s",
  async (terminal) => {
    const run = "new-run";
    const firstEvents: HistoryEvent[] = [
      {
        id: "retry-user",
        event_type: "user:message",
        run_id: run,
        timestamp: "2026-10-01T00:00:00Z",
        data: {
          content: "one retry question",
          attachments: [{ filename: "input.txt", path: "/input.txt" }],
        },
      },
      {
        id: "recent-answer",
        event_type: "message:chunk",
        run_id: run,
        timestamp: "2026-10-13T10:00:00Z",
        data: { content: "recent answer" },
      },
    ];
    const olderEvents: HistoryEvent[] = [
      {
        id: "retry-old-answer",
        event_type: "message:chunk",
        run_id: run,
        timestamp: "2026-10-02T00:00:00Z",
        data: { content: "old retry prefix " },
      },
      {
        id: "retry-old-tool",
        event_type: "tool:start",
        run_id: run,
        timestamp: "2026-10-02T00:00:01Z",
        data: {
          tool: "bash",
          tool_call_id: "old-tool",
          args: { cmd: "cat old.txt" },
        },
      },
      {
        id: "retry-old-result",
        event_type: "tool:result",
        run_id: run,
        timestamp: "2026-10-02T00:00:02Z",
        data: {
          tool: "bash",
          tool_call_id: "old-tool",
          result: { output: "old result", attachment: "old.txt" },
          success: true,
        },
      },
    ];
    const liveEvents: HistoryEvent[] = [
      {
        id: `${run}-live-text`,
        event_type: "message:chunk",
        run_id: run,
        timestamp: "2026-10-16T10:00:00Z",
        data: { run_id: run, content: " live text" },
      },
      {
        id: `${run}-live-tool-start`,
        event_type: "tool:start",
        run_id: run,
        timestamp: "2026-10-16T10:00:00Z",
        data: {
          run_id: run,
          tool: "bash",
          tool_call_id: "live-tool",
          args: { cmd: "printf live" },
        },
      },
      {
        id: `${run}-live-tool-result`,
        event_type: "tool:result",
        run_id: run,
        timestamp: "2026-10-16T10:00:00Z",
        data: {
          run_id: run,
          tool: "bash",
          tool_call_id: "live-tool",
          result: { output: "live result", attachment: "report.txt" },
          success: true,
        },
      },
      {
        id: `${run}-live-goal`,
        event_type: "goal:start",
        run_id: run,
        timestamp: "2026-10-16T10:00:00Z",
        data: {
          run_id: run,
          goal: { objective: "live objective", rubric: "live rubric" },
        },
      },
      ...(terminal
        ? [
            {
              id: `${run}-live-done`,
              event_type: "done",
              run_id: run,
              timestamp: "2026-10-16T10:00:00Z",
              data: { run_id: run },
            },
          ]
        : []),
    ];
    let resolveOlder!: (value: ReturnType<typeof latestWindow>) => void;
    mocks.events.mockImplementation(
      async (_id: string, options: { before_trace_id?: string }) =>
        options.before_trace_id
          ? new Promise<ReturnType<typeof latestWindow>>((resolve) => {
              resolveOlder = resolve;
            })
          : { ...latestWindow(), events: firstEvents },
    );
    const { result } = renderHook(() => useAgent());
    await act(async () => {
      await result.current.loadHistory("C");
    });
    let older!: Promise<void>;
    act(() => {
      older = result.current.loadOlderHistory();
    });
    await act(async () => {
      emitLiveReply(mocks.connect.mock.calls[0], run, terminal);
    });
    expect(
      result.current.messages.find((message) => message.role === "assistant")
        ?.content,
    ).toBe("recent answer live text");
    await act(async () => {
      resolveOlder({
        ...latestWindow(),
        events: olderEvents,
        has_more_traces: false,
      });
      await older;
    });
    let expected = reconstructMessagesFromEvents(
      [...firstEvents, ...olderEvents, ...liveEvents],
      new Set(),
      { activeSubagentStack: [] },
    );
    if (!terminal)
      expected = prepareMessagesForRunningRun(expected, run).messages;
    const project = (messages: typeof result.current.messages) =>
      messages.map((message) => ({
        id: message.id,
        role: message.role,
        runId: message.runId,
        content: message.content,
        timestamp: message.timestamp,
        parts: message.parts,
        attachments: message.attachments,
        cancelled: message.cancelled,
        isStreaming: message.isStreaming,
      }));
    expect(project(result.current.messages)).toEqual(project(expected));
    const assistant = result.current.messages.find(
      (message) => message.role === "assistant",
    );
    expect(assistant?.content).toBe("old retry prefix recent answer live text");
    expect(
      assistant?.parts
        ?.filter((part) => part.type === "tool")
        .map((part) => part.id),
    ).toEqual(["old-tool", "live-tool"]);
    expect(result.current.goalsByRunId[run]).toMatchObject({
      objective: "live objective",
      rubric: "live rubric",
    });
    expect(result.current.hasMoreHistoryTraces).toBe(false);
  },
);

test("accepted approval is replayed without repeating its external callback and cleared owners cannot append", async () => {
  let resolveOlder!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementation(
    async (_id: string, options: { before_trace_id?: string }) =>
      options.before_trace_id
        ? new Promise<ReturnType<typeof latestWindow>>((resolve) => {
            resolveOlder = resolve;
          })
        : latestWindow(),
  );
  const onApprovalRequired = vi.fn();
  const { result } = renderHook(() => useAgent({ onApprovalRequired }));
  await act(async () => {
    await result.current.loadHistory("C");
  });
  const call = mocks.connect.mock.calls[0];
  const context = call[3] as EventHandlerContext;
  let older!: Promise<void>;
  act(() => {
    older = result.current.loadOlderHistory();
  });
  await act(async () => {
    handleStreamEvent(
      {
        event: "approval_required",
        data: JSON.stringify({
          id: "once",
          message: "confirm",
          fields: [],
          run_id: "new-run",
          _source_id: "approval-source",
        }),
      },
      call[2],
      "approval-live",
      "2026-10-16T00:00:00Z",
      context,
    );
  });
  expect(onApprovalRequired).toHaveBeenCalledOnce();
  await act(async () => {
    resolveOlder({
      ...latestWindow(),
      events: events("older-run", "2026-10-01T10:00:00Z"),
      has_more_traces: false,
    });
    await older;
  });
  expect(onApprovalRequired).toHaveBeenCalledOnce();
  expect(
    result.current.messages
      .find(
        (message) =>
          message.runId === "new-run" && message.role === "assistant",
      )
      ?.parts?.find((part) => part.type === "tool" && part.id === "once"),
  ).toMatchObject({ name: "ask_human", isPending: true });
  act(() => result.current.clearMessages());
  await act(async () => {
    emitLiveReply(call, "new-run", false);
  });
  expect(result.current.messages).toEqual([]);
  expect(result.current.activeGoal).toBeNull();
  expect(result.current.goalsByRunId).toEqual({});
});

test("same-batch done and older response cannot restore streaming from a stale messages ref", async () => {
  let resolveOlder!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementation(
    async (_id: string, options: { before_trace_id?: string }) =>
      options.before_trace_id
        ? new Promise<ReturnType<typeof latestWindow>>((resolve) => {
            resolveOlder = resolve;
          })
        : latestWindow(),
  );
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("C");
  });
  const call = mocks.connect.mock.calls[0];
  let older!: Promise<void>;
  act(() => {
    older = result.current.loadOlderHistory();
  });
  await act(async () => {
    handleStreamEvent(
      {
        event: "done",
        data: JSON.stringify({ run_id: "new-run", _source_id: "terminal" }),
      },
      call[2],
      "done-batch",
      "2026-10-16T00:00:00Z",
      call[3],
    );
    resolveOlder({
      ...latestWindow(),
      events: events("older-run", "2026-10-01T10:00:00Z"),
      has_more_traces: false,
    });
    await older;
  });
  expect(
    result.current.messages.find(
      (message) => message.role === "assistant" && message.runId === "new-run",
    )?.isStreaming,
  ).toBe(false);
  expect(
    result.current.messages.some(
      (message) => message.content === "answer-older-run",
    ),
  ).toBe(true);
  expect(result.current.hasMoreHistoryTraces).toBe(false);
});

test("stored coverage does not consume the first actual done effects or repeat them for Redis retries", async () => {
  let resolveOlder!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementation(
    async (_id: string, options: { before_trace_id?: string }) =>
      options.before_trace_id
        ? new Promise<ReturnType<typeof latestWindow>>((resolve) => {
            resolveOlder = resolve;
          })
        : latestWindow(),
  );
  const onStreamDone = vi.fn();
  const { result } = renderHook(() => useAgent({ onStreamDone }));
  await act(async () => {
    await result.current.loadHistory("C");
  });
  const call = mocks.connect.mock.calls[0];
  let older!: Promise<void>;
  act(() => {
    older = result.current.loadOlderHistory();
  });
  await act(async () => {
    resolveOlder({
      ...latestWindow(),
      events: [
        {
          id: "stored-done",
          trace_id: "live-trace",
          run_id: "new-run",
          event_type: "done",
          timestamp: "2026-10-16T00:00:00Z",
          data: { _source_id: "terminal" },
        },
      ],
      has_more_traces: false,
    });
    await older;
  });
  expect(onStreamDone).not.toHaveBeenCalled();
  expect(mocks.streamMarkRead).not.toHaveBeenCalled();
  await act(async () => {
    for (const id of ["redis-done", "redis-done-retry"])
      handleStreamEvent(
        {
          event: "done",
          data: JSON.stringify({
            run_id: "new-run",
            _source_id: "terminal",
            _source_trace_id: "live-trace",
          }),
        },
        call[2],
        id,
        "2026-10-16T00:00:00Z",
        call[3],
      );
  });
  expect(onStreamDone).toHaveBeenCalledOnce();
  expect(mocks.streamMarkRead).toHaveBeenCalledOnce();
  expect(
    result.current.messages.find(
      (message) => message.role === "assistant" && message.runId === "new-run",
    )?.isStreaming,
  ).toBe(false);
});

test("an active shell without journal events keeps its id and accepts its first chunk after paging", async () => {
  let resolveOlder!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementation(
    async (_id: string, options: { before_trace_id?: string }) =>
      options.before_trace_id
        ? new Promise<ReturnType<typeof latestWindow>>((resolve) => {
            resolveOlder = resolve;
          })
        : {
            ...latestWindow(),
            events: [events("new-run", "2026-10-13T10:00:00Z")[0]],
          },
  );
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("C");
  });
  const call = mocks.connect.mock.calls[0];
  const shell = result.current.messages.find(
    (message) => message.role === "assistant",
  );
  expect(shell?.id).toBe(call[2]);
  let older!: Promise<void>;
  act(() => {
    older = result.current.loadOlderHistory();
  });
  await act(async () => {
    resolveOlder({
      ...latestWindow(),
      events: events("older-run", "2026-10-01T10:00:00Z"),
      has_more_traces: false,
    });
    await older;
  });
  expect(
    result.current.messages.find(
      (message) => message.role === "assistant" && message.runId === "new-run",
    ),
  ).toMatchObject({
    id: shell?.id,
    timestamp: shell?.timestamp,
    content: "",
    isStreaming: true,
  });
  await act(async () => {
    handleStreamEvent(
      {
        event: "message:chunk",
        data: JSON.stringify({
          content: "first chunk",
          run_id: "new-run",
          _source_id: "first",
        }),
      },
      call[2],
      "first",
      "2026-10-16T00:00:00Z",
      call[3],
    );
  });
  expect(
    result.current.messages.find(
      (message) => message.role === "assistant" && message.runId === "new-run",
    ),
  ).toMatchObject({
    id: shell?.id,
    timestamp: shell?.timestamp,
    content: "first chunk",
    isStreaming: true,
  });
});

test("paging later does not reset accepted subagent timestamps when payload timestamp was absent", async () => {
  let resolveOlder!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementation(
    async (_id: string, options: { before_trace_id?: string }) =>
      options.before_trace_id
        ? new Promise<ReturnType<typeof latestWindow>>((resolve) => {
            resolveOlder = resolve;
          })
        : latestWindow(),
  );
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("C");
  });
  const call = mocks.connect.mock.calls[0];
  const clock = vi
    .spyOn(Date, "now")
    .mockReturnValue(Date.parse("2026-10-16T00:00:00Z"));
  try {
    let older!: Promise<void>;
    act(() => {
      older = result.current.loadOlderHistory();
    });
    await act(async () => {
      handleStreamEvent(
        {
          event: "agent:call",
          data: JSON.stringify({
            run_id: "new-run",
            agent_id: "worker",
            agent_name: "Worker",
            depth: 1,
            input: "task",
            _source_id: "agent-call",
          }),
        },
        call[2],
        "agent-call",
        "2026-10-16T00:00:00Z",
        call[3],
      );
      clock.mockReturnValue(Date.parse("2026-10-16T00:00:02Z"));
      handleStreamEvent(
        {
          event: "agent:result",
          data: JSON.stringify({
            run_id: "new-run",
            agent_id: "worker",
            depth: 1,
            result: "complete",
            success: true,
            _source_id: "agent-result",
          }),
        },
        call[2],
        "agent-result",
        "2026-10-16T00:00:02Z",
        call[3],
      );
    });
    const original = result.current.messages
      .find(
        (message) =>
          message.role === "assistant" && message.runId === "new-run",
      )
      ?.parts?.find((part) => part.type === "subagent");
    expect(original).toMatchObject({
      startedAt: Date.parse("2026-10-16T00:00:00Z"),
      completedAt: Date.parse("2026-10-16T00:00:02Z"),
    });
    clock.mockReturnValue(Date.parse("2026-10-16T00:10:00Z"));
    await act(async () => {
      resolveOlder({
        ...latestWindow(),
        events: events("older-run", "2026-10-01T10:00:00Z"),
        has_more_traces: false,
      });
      await older;
    });
    expect(
      result.current.messages
        .find(
          (message) =>
            message.role === "assistant" && message.runId === "new-run",
        )
        ?.parts?.find((part) => part.type === "subagent"),
    ).toEqual(original);
  } finally {
    clock.mockRestore();
  }
});

test("a covered steer keeps the original SSE target attached to the newest turn after paging", async () => {
  const run = "new-run";
  const at = (second: number) => `2026-10-16T00:00:0${second}Z`;
  const stored: HistoryEvent[] = [
    {
      id: "user",
      trace_id: "trace",
      seq: 1,
      event_type: "user:message",
      run_id: run,
      timestamp: "2026-10-13T00:00:00Z",
      data: { content: "question", _source_id: "u" },
    },
    {
      id: "before",
      trace_id: "trace",
      seq: 2,
      event_type: "message:chunk",
      run_id: run,
      timestamp: "2026-10-13T00:00:01Z",
      data: { content: "before", _source_id: "b" },
    },
    {
      id: "steer",
      trace_id: "trace",
      seq: 3,
      event_type: "steer:message",
      run_id: run,
      timestamp: at(1),
      data: {
        content: "follow up",
        message_id: "steer-1",
        created_at: at(1),
        _source_id: "s",
      },
    },
    {
      id: "after",
      trace_id: "trace",
      seq: 4,
      event_type: "message:chunk",
      run_id: run,
      timestamp: at(2),
      data: { content: "after", _source_id: "a" },
    },
  ];
  let resolveOlder!: (value: ReturnType<typeof latestWindow>) => void;
  mocks.events.mockImplementation(
    async (_id: string, options: { before_trace_id?: string }) =>
      options.before_trace_id
        ? new Promise<ReturnType<typeof latestWindow>>((resolve) => {
            resolveOlder = resolve;
          })
        : { ...latestWindow(), events: stored.slice(0, 2) },
  );
  const { result } = renderHook(() => useAgent());
  await act(async () => {
    await result.current.loadHistory("C");
  });
  const call = mocks.connect.mock.calls[0];
  let older!: Promise<void>;
  act(() => {
    older = result.current.loadOlderHistory();
  });
  await act(async () => {
    handleStreamEvent(
      {
        event: "steer:message",
        data: JSON.stringify({
          ...(stored[2].data as object),
          run_id: run,
          _source_trace_id: "trace",
        }),
      },
      call[2],
      "redis-steer",
      at(1),
      call[3],
    );
    handleStreamEvent(
      {
        event: "message:chunk",
        data: JSON.stringify({
          ...(stored[3].data as object),
          run_id: run,
          _source_trace_id: "trace",
        }),
      },
      call[2],
      "redis-after",
      at(2),
      call[3],
    );
  });
  expect(
    result.current.messages
      .filter((message) => message.role === "assistant")
      .map((message) => message.content),
  ).toEqual(["before", "after"]);
  await act(async () => {
    resolveOlder({ ...latestWindow(), events: stored, has_more_traces: false });
    await older;
  });
  await act(async () => {
    handleStreamEvent(
      {
        event: "message:chunk",
        data: JSON.stringify({
          run_id: run,
          content: "+tail",
          _source_id: "tail",
        }),
      },
      call[2],
      "redis-tail",
      at(3),
      call[3],
    );
    handleStreamEvent(
      {
        event: "tool:start",
        data: JSON.stringify({
          run_id: run,
          tool: "bash",
          tool_call_id: "newest-tool",
          args: { cmd: "pwd" },
          _source_id: "newest-tool",
        }),
      },
      call[2],
      "redis-tool",
      at(4),
      call[3],
    );
  });
  const assistants = result.current.messages.filter(
    (message) => message.role === "assistant",
  );
  expect(assistants.map((message) => message.content)).toEqual([
    "before",
    "after+tail",
  ]);
  expect(assistants[1].id).toBe(call[2]);
  expect(
    assistants[0].parts?.some(
      (part) => part.type === "tool" && part.id === "newest-tool",
    ),
  ).toBe(false);
  expect(
    assistants[1].parts?.find(
      (part) => part.type === "tool" && part.id === "newest-tool",
    ),
  ).toMatchObject({ args: { cmd: "pwd" } });
  expect(
    result.current.messages.filter((message) => message.id === call[2]),
  ).toHaveLength(1);
});
