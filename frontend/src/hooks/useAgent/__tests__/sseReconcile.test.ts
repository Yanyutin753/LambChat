import { beforeEach, vi } from "vitest";
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
  type StreamReconcileContext,
} from "../sseReconcile.ts";
import {
  connectToSSE,
  type SSEConnectionContext,
} from "../sseConnection.ts";

beforeEach(() => {
  vi.resetAllMocks();
  mocks.getValidAccessToken.mockResolvedValue("token-a");
  mocks.fetchEventSource.mockResolvedValue(undefined);
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
        onmessage: (event: { event: string; data?: string; id?: string }) => void;
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
