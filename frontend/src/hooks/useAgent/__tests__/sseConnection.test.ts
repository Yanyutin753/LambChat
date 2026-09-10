import { vi } from "vitest";
import type { Message } from "../../../types";

const mocks = vi.hoisted(() => ({
  fetchEventSource: vi.fn(),
  getValidAccessToken: vi.fn(),
  getStatus: vi.fn(),
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
    markRead: vi.fn(),
  },
}));

import {
  connectToSSE,
  getSSECloseAction,
  isTerminalSSEEvent,
  reconnectSSE,
  type SSEConnectionContext,
} from "../sseConnection.ts";

test("retries an SSE close that arrives before a terminal stream event", () => {
  expect(
    getSSECloseAction({
      receivedTerminalEvent: false,
    }),
  ).toBe("retry");
});

test("treats SSE close as terminal only after done or task error", () => {
  expect(isTerminalSSEEvent("message:chunk")).toBe(false);
  expect(isTerminalSSEEvent("done")).toBe(true);
  expect(isTerminalSSEEvent("complete")).toBe(true);
  expect(isTerminalSSEEvent("user:cancel")).toBe(false);
  expect(isTerminalSSEEvent("error", { type: "ValueError" })).toBe(true);

  expect(
    getSSECloseAction({
      receivedTerminalEvent: true,
    }),
  ).toBe("terminal");
});

test("does not treat transport-level SSE errors as terminal task events", () => {
  expect(
    isTerminalSSEEvent("error", { error: "An internal error occurred" }),
  ).toBe(false);
});

test("a stale connection cannot start after token acquisition resolves", async () => {
  let resolveToken: (token: string | null) => void = () => undefined;
  mocks.getValidAccessToken.mockReturnValueOnce(
    new Promise<string | null>((resolve) => {
      resolveToken = resolve;
    }),
  );
  const statuses: string[] = [];
  const ctx = {
    abortControllerRef: { current: null },
    sseGenerationRef: { current: 0 },
    isConnectingRef: { current: false },
    streamingMessageIdRef: { current: null },
    reconnectTimeoutRef: { current: null },
    retryCountRef: { current: 0 },
    messagesRef: { current: [] },
    setConnectionStatus: (status: string) => statuses.push(status),
  } as unknown as SSEConnectionContext;

  const connection = connectToSSE("session-a", "run-a", "assistant-a", ctx);
  ctx.sseGenerationRef.current += 1;
  resolveToken("token-a");
  await connection;

  expect(mocks.fetchEventSource).not.toHaveBeenCalled();
  expect(statuses).toEqual([]);
});

function createReconnectContext(messages: Message[]) {
  let currentMessages = messages;
  const onStaleRunStateDetected = vi.fn();
  const ctx = {
    abortControllerRef: { current: null },
    sseGenerationRef: { current: 0 },
    isConnectingRef: { current: false },
    streamingMessageIdRef: { current: "assistant-a" },
    reconnectTimeoutRef: { current: null },
    retryCountRef: { current: 0 },
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
  } as unknown as SSEConnectionContext & {
    onStaleRunStateDetected: ReturnType<typeof vi.fn>;
    readMessages: () => Message[];
  };
  return {
    ctx,
    onStaleRunStateDetected,
    readMessages: () => currentMessages,
  };
}

test("reconnect drops an empty streaming bubble and reloads history when the run completed", async () => {
  mocks.getStatus.mockResolvedValueOnce({ status: "completed" });
  const { ctx, onStaleRunStateDetected, readMessages } = createReconnectContext([
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
  ]);

  await reconnectSSE(
    ctx as Parameters<typeof reconnectSSE>[0],
    "run-a",
  );

  expect(readMessages().map((message) => message.id)).toEqual(["run-a:user"]);
  expect(onStaleRunStateDetected).toHaveBeenCalledWith("run-a");
});

test("reconnect keeps a settled answer and does not reload history", async () => {
  mocks.getStatus.mockResolvedValueOnce({ status: "completed" });
  const { ctx, onStaleRunStateDetected, readMessages } = createReconnectContext([
    {
      id: "run-a:user",
      role: "user",
      content: "hello",
      timestamp: new Date("2026-09-10T02:59:59.000Z"),
    },
    {
      id: "assistant-a",
      role: "assistant",
      content: "final answer",
      timestamp: new Date("2026-09-10T03:00:00.000Z"),
      parts: [],
      isStreaming: false,
    },
  ]);

  await reconnectSSE(
    ctx as Parameters<typeof reconnectSSE>[0],
    "run-a",
  );

  expect(readMessages().map((message) => message.id)).toEqual([
    "run-a:user",
    "assistant-a",
  ]);
  expect(onStaleRunStateDetected).not.toHaveBeenCalled();
});
