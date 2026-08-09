import { vi } from "vitest";

const mocks = vi.hoisted(() => ({
  fetchEventSource: vi.fn(),
  getValidAccessToken: vi.fn(),
}));

vi.mock("@microsoft/fetch-event-source", () => ({
  fetchEventSource: mocks.fetchEventSource,
}));

vi.mock("../../../services/api/tokenManager", () => ({
  getValidAccessToken: mocks.getValidAccessToken,
  refreshAccessToken: vi.fn(),
}));

import {
  connectToSSE,
  getSSECloseAction,
  isTerminalSSEEvent,
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
