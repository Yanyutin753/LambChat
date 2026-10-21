/** @vitest-environment jsdom */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
import type { Message } from "../../../types";

const mocks = vi.hoisted(() => ({
  fetchEventSource: vi.fn(),
  getValidAccessToken: vi.fn(),
  getStatus: vi.fn(),
  get: vi.fn(),
}));

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: mocks.fetchEventSource,
}));

vi.mock("../../../services/api/tokenManager", () => ({
  getValidAccessToken: mocks.getValidAccessToken,
  refreshAccessToken: vi.fn(),
}));

vi.mock("../../../services/api", () => ({
  sessionApi: {
    getStatus: mocks.getStatus,
    get: mocks.get,
    markRead: vi.fn(),
  },
}));

import {
  STREAM_STALE_THRESHOLD_MS,
  isStreamActivityStale,
  reconcileActiveStream,
  reconcileOpenSession,
  shouldReloadOpenSession,
  useStreamReconcile,
  type StreamReconcileContext,
} from "../sseReconcile.ts";
import { connectToSSE, type SSEConnectionContext } from "../sseConnection.ts";

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getValidAccessToken.mockResolvedValue("token-a");
  mocks.fetchEventSource.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

test("stream activity goes stale only after the heartbeat window passes", () => {
  expect(isStreamActivityStale(null, Date.now())).toBe(false);
  expect(
    isStreamActivityStale(
      Date.now() - (STREAM_STALE_THRESHOLD_MS - 1),
      Date.now(),
    ),
  ).toBe(false);
  expect(
    isStreamActivityStale(
      Date.now() - (STREAM_STALE_THRESHOLD_MS + 1),
      Date.now(),
    ),
  ).toBe(true);
});

test("open session reloads only when the server knows a newer run", () => {
  expect(
    shouldReloadOpenSession({
      serverRunId: "run-b",
      localRunId: "run-a",
    }),
  ).toBe(true);
  expect(
    shouldReloadOpenSession({
      serverRunId: "run-a",
      localRunId: "run-a",
    }),
  ).toBe(false);
  expect(
    shouldReloadOpenSession({
      serverRunId: null,
      localRunId: "run-a",
    }),
  ).toBe(false);
  expect(
    shouldReloadOpenSession({
      serverRunId: "run-b",
      localRunId: null,
    }),
  ).toBe(true);
});

test("an idle-session probe cannot reload over a user send that began while awaiting the server", async () => {
  let release!: (value: unknown) => void;
  mocks.get.mockReturnValueOnce(
    new Promise((resolve) => {
      release = resolve;
    }),
  );
  const { ctx } = createReconcileContext([], {
    currentRunIdRef: { current: null },
  });
  const loadHistory = vi.fn();
  let busy = false;
  const pending = reconcileOpenSession(ctx, {
    loadHistory,
    isSending: false,
    isLoadingHistory: false,
    isBusy: () => busy,
  });
  busy = true;
  release({ metadata: { current_run_id: "old-server-run" } });
  await pending;
  expect(loadHistory).not.toHaveBeenCalled();
});

function createReconcileContext(
  messages: Message[],
  overrides: Record<string, unknown> = {},
) {
  let currentMessages = messages;
  const onStaleRunStateDetected = vi.fn();
  const ctx = {
    abortControllerRef: { current: null },
    sseGenerationRef: { current: 0 },
    isConnectingRef: { current: false },
    streamingMessageIdRef: { current: "assistant-a" },
    reconnectTimeoutRef: { current: null },
    retryCountRef: { current: 0 },
    lastStreamActivityAtRef: { current: null },
    sessionIdRef: { current: "session-a" },
    currentRunIdRef: { current: "run-a" },
    isReconnectFromHistoryRef: { current: false },
    messagesRef: {
      get current() {
        return currentMessages;
      },
    },
    setMessages: (updater: React.SetStateAction<Message[]>) => {
      currentMessages =
        typeof updater === "function" ? updater(currentMessages) : updater;
    },
    setConnectionStatus: () => undefined,
    setIsInitializingSandbox: () => undefined,
    setSessionId: () => undefined,
    setActiveGoal: () => undefined,
    setGoalsByRunId: () => undefined,
    onStaleRunStateDetected,
    ...overrides,
  } as unknown as StreamReconcileContext;
  return { ctx, onStaleRunStateDetected, readMessages: () => currentMessages };
}

function streamingBubble(): Message[] {
  return [
    {
      id: "run-a:user",
      role: "user",
      content: "hello",
      timestamp: new Date("2026-09-10T02:59:59.000Z"),
    },
    {
      id: "assistant-a",
      role: "assistant",
      content: "",
      timestamp: new Date("2026-09-10T03:00:00.000Z"),
      parts: [],
      isStreaming: true,
    },
  ];
}

test("reconcile settles a remotely finished run and reloads missing content", async () => {
  mocks.getStatus.mockResolvedValue({ status: "completed" });
  const { ctx, onStaleRunStateDetected, readMessages } =
    createReconcileContext(streamingBubble());

  const stillRunning = await reconcileActiveStream(ctx);

  expect(stillRunning).toBe(false);
  expect(readMessages().map((message) => message.id)).toEqual(["run-a:user"]);
  expect(onStaleRunStateDetected).toHaveBeenCalledWith("run-a");
});

test.each(["cancelled", "failed", "expired"])(
  "watchdog settles a %s run without reconnecting to a dead stream",
  async (status) => {
    mocks.getStatus.mockResolvedValue({ status });
    const { ctx, readMessages } = createReconcileContext(streamingBubble());

    expect(
      await reconcileActiveStream(ctx, { connectionStatus: "disconnected" }),
    ).toBe(false);
    expect(ctx.streamingMessageIdRef.current).toBeNull();
    expect(readMessages().map((message) => message.id)).toEqual(["run-a:user"]);
    expect(mocks.fetchEventSource).not.toHaveBeenCalled();
  },
);

test("reconcile forces a reconnect when the live run went silent mid-stream", async () => {
  mocks.getStatus.mockResolvedValue({ status: "running" });
  const { ctx } = createReconcileContext(streamingBubble(), {
    lastStreamActivityAtRef: {
      current: Date.now() - (STREAM_STALE_THRESHOLD_MS + 5_000),
    },
  });

  const stillRunning = await reconcileActiveStream(ctx);

  expect(stillRunning).toBe(true);
  expect(mocks.fetchEventSource).toHaveBeenCalledTimes(1);
});

test("reconcile forces a reconnect when the transport dropped", async () => {
  mocks.getStatus.mockResolvedValue({ status: "running" });
  const { ctx } = createReconcileContext(streamingBubble(), {
    lastStreamActivityAtRef: { current: Date.now() },
  });

  // 传输层已断（disconnected），即使活跃时间戳还新鲜也要重连
  const stillRunning = await reconcileActiveStream(ctx, {
    connectionStatus: "disconnected",
  });

  expect(stillRunning).toBe(true);
  expect(mocks.fetchEventSource).toHaveBeenCalledTimes(1);
});

test("reconcile leaves a healthy live stream alone", async () => {
  mocks.getStatus.mockResolvedValue({ status: "running" });
  const { ctx } = createReconcileContext(streamingBubble(), {
    lastStreamActivityAtRef: { current: Date.now() },
  });

  const stillRunning = await reconcileActiveStream(ctx, {
    connectionStatus: "connected",
  });

  expect(stillRunning).toBe(true);
  expect(mocks.fetchEventSource).not.toHaveBeenCalled();
});

test("reconcile defers to the backoff reconnect path when the status probe fails", async () => {
  mocks.getStatus.mockRejectedValue(new Error("network down"));
  const { ctx } = createReconcileContext(streamingBubble());
  vi.useFakeTimers();
  try {
    const stillRunning = await reconcileActiveStream(ctx);
    expect(stillRunning).toBe(true);
  } finally {
    vi.useRealTimers();
  }
});

test("open-session reconcile reloads history when the server moved on", async () => {
  mocks.get.mockResolvedValue({
    id: "session-a",
    metadata: { current_run_id: "run-b" },
  });
  const loadHistory = vi.fn().mockResolvedValue(null);
  const { ctx } = createReconcileContext([]);

  await reconcileOpenSession(ctx, {
    loadHistory,
    isSending: false,
    isLoadingHistory: false,
  });

  expect(loadHistory).toHaveBeenCalledWith("session-a");
});

test("open-session reconcile skips while a send or load is in flight", async () => {
  const loadHistory = vi.fn();
  const { ctx } = createReconcileContext([]);

  await reconcileOpenSession(ctx, {
    loadHistory,
    isSending: true,
    isLoadingHistory: false,
  });
  await reconcileOpenSession(ctx, {
    loadHistory,
    isSending: false,
    isLoadingHistory: true,
  });

  expect(loadHistory).not.toHaveBeenCalled();
  expect(mocks.get).not.toHaveBeenCalled();
});

test("open-session reconcile tolerates a failing session fetch", async () => {
  mocks.get.mockRejectedValue(new Error("offline"));
  const loadHistory = vi.fn();
  const { ctx } = createReconcileContext([]);

  await expect(
    reconcileOpenSession(ctx, {
      loadHistory,
      isSending: false,
      isLoadingHistory: false,
    }),
  ).resolves.toBeUndefined();
  expect(loadHistory).not.toHaveBeenCalled();
});

test("open-session reconcile keeps a session the server has not advanced", async () => {
  mocks.get.mockResolvedValue({
    id: "session-a",
    metadata: { current_run_id: "run-a" },
  });
  const loadHistory = vi.fn();
  const { ctx } = createReconcileContext([]);

  await reconcileOpenSession(ctx, {
    loadHistory,
    isSending: false,
    isLoadingHistory: false,
  });

  expect(loadHistory).not.toHaveBeenCalled();
});

test("connectToSSE records stream activity for every event including ping", async () => {
  mocks.fetchEventSource.mockImplementationOnce(
    async (
      _url: string,
      config: {
        onopen?: (response: { status: number; ok: boolean }) => void;
        onmessage: (event: {
          event: string;
          data?: string;
          id?: string;
        }) => void;
      },
    ) => {
      config.onopen?.({ status: 200, ok: true });
      config.onmessage({ event: "ping" });
      return undefined;
    },
  );
  const { ctx } = createReconcileContext(streamingBubble());
  ctx.lastStreamActivityAtRef.current = 0;

  await connectToSSE(
    "session-a",
    "run-a",
    "assistant-a",
    ctx as unknown as SSEConnectionContext,
  );

  expect(ctx.lastStreamActivityAtRef.current).toBeGreaterThan(0);
});

test("remote settlement invalidates and aborts the old stream before ending the bubble", async () => {
  mocks.getStatus.mockResolvedValue({ status: "completed" });
  const controller = new AbortController();
  const { ctx } = createReconcileContext(streamingBubble(), {
    abortControllerRef: { current: controller },
    isConnectingRef: { current: true },
  });
  await reconcileActiveStream(ctx);
  expect(controller.signal.aborted).toBe(true);
  expect(ctx.sseGenerationRef.current).toBe(1);
  expect(ctx.isConnectingRef.current).toBe(false);
});

test("a delayed terminal probe cannot settle a replacement stream", async () => {
  let resolveStatus: (value: { status: string }) => void = () => undefined;
  mocks.getStatus.mockReturnValueOnce(
    new Promise((resolve) => {
      resolveStatus = resolve;
    }),
  );
  const { ctx, readMessages } = createReconcileContext(streamingBubble());
  const probe = reconcileActiveStream(ctx);
  ctx.sseGenerationRef.current += 1;
  resolveStatus({ status: "completed" });
  await probe;
  expect(readMessages()[1].isStreaming).toBe(true);
});

function mountReconcile(
  ctx: StreamReconcileContext,
  connectionStatus: "connected" | "reconnecting" | "disconnected",
) {
  return renderHook(() =>
    useStreamReconcile({
      createSSEContext: () => ctx,
      sessionIdRef: ctx.sessionIdRef,
      currentRunIdRef: ctx.currentRunIdRef,
      isReconnectFromHistoryRef: ctx.isReconnectFromHistoryRef,
      streamingMessageIdRef: ctx.streamingMessageIdRef,
      connectionStatus,
      setConnectionStatus: ctx.setConnectionStatus,
      isSendingRef: { current: false },
      isLoadingHistoryRef: { current: false },
      loadHistoryRef: { current: vi.fn().mockResolvedValue(null) },
    }),
  );
}

test("foreground recovery can settle a run while its replacement SSE remains open", async () => {
  vi.useFakeTimers();
  mocks.getStatus
    .mockResolvedValueOnce({ status: "running" })
    .mockResolvedValue({ status: "completed" });
  mocks.fetchEventSource.mockImplementation(
    (_url, config) =>
      new Promise<void>((resolve) => {
        config.signal.addEventListener("abort", () => resolve());
      }),
  );
  const { ctx, readMessages, onStaleRunStateDetected } =
    createReconcileContext(streamingBubble());
  const { result } = mountReconcile(ctx, "disconnected");

  await act(async () => {
    void result.current();
  });
  expect(mocks.fetchEventSource).toHaveBeenCalledTimes(1);
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3_001);
  });
  await act(async () => {
    window.dispatchEvent(new Event("focus"));
  });

  expect(ctx.streamingMessageIdRef.current).toBeNull();
  expect(readMessages().every((message) => !message.isStreaming)).toBe(true);
  expect(onStaleRunStateDetected).toHaveBeenCalledWith("run-a");
});

test.each(["reconnecting", "disconnected"] as const)(
  "watchdog recovers a %s stream without another foreground event",
  async (status) => {
    vi.useFakeTimers();
    mocks.getStatus.mockResolvedValue({ status: "completed" });
    const { ctx, onStaleRunStateDetected } =
      createReconcileContext(streamingBubble());
    mountReconcile(ctx, status);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });

    expect(ctx.streamingMessageIdRef.current).toBeNull();
    expect(onStaleRunStateDetected).toHaveBeenCalledWith("run-a");
  },
);

test("restoring a cached page reconciles the current run", async () => {
  mocks.getStatus.mockResolvedValue({ status: "completed" });
  const { ctx, onStaleRunStateDetected } =
    createReconcileContext(streamingBubble());
  mountReconcile(ctx, "connected");

  await act(async () => {
    window.dispatchEvent(new Event("pageshow"));
  });

  expect(ctx.streamingMessageIdRef.current).toBeNull();
  expect(onStaleRunStateDetected).toHaveBeenCalledWith("run-a");
});

test("a delayed open-session probe cannot navigate back after switching conversations", async () => {
  let resolveSession!: (value: unknown) => void;
  mocks.get.mockReturnValueOnce(
    new Promise((resolve) => {
      resolveSession = resolve;
    }),
  );
  const { ctx } = createReconcileContext([]);
  const loadHistory = vi.fn();
  const pending = reconcileOpenSession(ctx, {
    loadHistory,
    isSending: false,
    isLoadingHistory: false,
  });
  ctx.sessionIdRef.current = "session-b";
  ctx.currentRunIdRef.current = "run-b";
  ctx.sseGenerationRef.current += 1;
  resolveSession({
    id: "session-a",
    metadata: { current_run_id: "new-run-a" },
  });
  await pending;

  expect(loadHistory).not.toHaveBeenCalled();
});

test("an idle open conversation discovers a scheduled run without a foreground event", async () => {
  vi.useFakeTimers();
  mocks.get.mockResolvedValue({
    id: "session-a",
    metadata: { current_run_id: "scheduled-run", task_status: "running" },
  });
  const { ctx } = createReconcileContext([], {
    currentRunIdRef: { current: null },
    streamingMessageIdRef: { current: null },
  });
  const loadHistory = vi.fn().mockResolvedValue(null);
  renderHook(() =>
    useStreamReconcile({
      createSSEContext: () => ctx,
      sessionIdRef: ctx.sessionIdRef,
      currentRunIdRef: ctx.currentRunIdRef,
      isReconnectFromHistoryRef: ctx.isReconnectFromHistoryRef,
      streamingMessageIdRef: ctx.streamingMessageIdRef,
      connectionStatus: "disconnected",
      setConnectionStatus: ctx.setConnectionStatus,
      isSendingRef: { current: false },
      isLoadingHistoryRef: { current: false },
      loadHistoryRef: { current: loadHistory },
    }),
  );

  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });

  expect(loadHistory).toHaveBeenCalledWith("session-a");
});

test("idle history refresh retains the explicitly requested older execution", async () => {
  vi.useFakeTimers();
  mocks.get.mockResolvedValue({
    id: "session-a",
    metadata: { current_run_id: "latest-run", task_status: "completed" },
  });
  const { ctx } = createReconcileContext([], {
    currentRunIdRef: { current: "requested-old-run" },
    streamingMessageIdRef: { current: null },
  });
  const loadHistory = vi.fn().mockResolvedValue(null);
  renderHook(() =>
    useStreamReconcile({
      createSSEContext: () => ctx,
      sessionIdRef: ctx.sessionIdRef,
      currentRunIdRef: ctx.currentRunIdRef,
      isReconnectFromHistoryRef: ctx.isReconnectFromHistoryRef,
      streamingMessageIdRef: ctx.streamingMessageIdRef,
      connectionStatus: "disconnected",
      setConnectionStatus: ctx.setConnectionStatus,
      isSendingRef: { current: false },
      isLoadingHistoryRef: { current: false },
      historyTargetRunIdRef: { current: "requested-old-run" },
      loadHistoryRef: { current: loadHistory },
    }),
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });
  expect(loadHistory).toHaveBeenCalledWith("session-a", "requested-old-run");
});

test("a pinned older run does not reload a latest completed reply already visible", async () => {
  mocks.get.mockResolvedValue({
    id: "session-a",
    metadata: { current_run_id: "latest-run", task_status: "completed" },
  });
  const latest = {
    id: "latest",
    role: "assistant",
    runId: "latest-run",
    content: "done",
    timestamp: new Date(),
  } as Message;
  const { ctx } = createReconcileContext([latest], {
    currentRunIdRef: { current: "requested-old-run" },
    streamingMessageIdRef: { current: null },
  });
  const loadHistory = vi.fn();
  await reconcileOpenSession(ctx, {
    loadHistory,
    targetRunId: "requested-old-run",
    isSending: false,
    isLoadingHistory: false,
  });
  expect(loadHistory).not.toHaveBeenCalled();
});

test("a run discovered while queued attaches when it starts with the same run ID", async () => {
  mocks.get.mockResolvedValue({
    id: "session-a",
    metadata: { current_run_id: "run-a", task_status: "running" },
  });
  const { ctx } = createReconcileContext([], {
    streamingMessageIdRef: { current: null },
  });
  const loadHistory = vi.fn().mockResolvedValue(null);

  await reconcileOpenSession(ctx, {
    loadHistory,
    isSending: false,
    isLoadingHistory: false,
  });

  expect(loadHistory).toHaveBeenCalledWith("session-a");
});

test("a scheduled run that finishes before attachment still loads its missing reply", async () => {
  mocks.get.mockResolvedValue({
    id: "session-a",
    metadata: { current_run_id: "run-a", task_status: "completed" },
  });
  const { ctx } = createReconcileContext([], {
    streamingMessageIdRef: { current: null },
  });
  const loadHistory = vi.fn().mockResolvedValue(null);

  await reconcileOpenSession(ctx, {
    loadHistory,
    isSending: false,
    isLoadingHistory: false,
  });

  expect(loadHistory).toHaveBeenCalledWith("session-a");
});

test("a completed reply already displayed is not reloaded on each idle probe", async () => {
  mocks.get.mockResolvedValue({
    id: "session-a",
    metadata: { current_run_id: "run-a", task_status: "completed" },
  });
  const { ctx } = createReconcileContext(
    [
      {
        id: "reply",
        role: "assistant",
        content: "已完成",
        runId: "run-a",
        timestamp: new Date(),
      },
    ],
    { streamingMessageIdRef: { current: null } },
  );
  const loadHistory = vi.fn().mockResolvedValue(null);

  await reconcileOpenSession(ctx, {
    loadHistory,
    isSending: false,
    isLoadingHistory: false,
  });

  expect(loadHistory).not.toHaveBeenCalled();
});
