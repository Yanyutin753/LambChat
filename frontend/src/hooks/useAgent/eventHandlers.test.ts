import assert from "node:assert/strict";
import test from "node:test";
import type { Message } from "../../types";
import { handleStreamEvent } from "./eventHandlers.ts";
import type { EventHandlerContext } from "./eventHandlers.ts";
import type { StreamEvent } from "./types.ts";
import { prepareMessagesForRunningRun } from "./historyLoader.ts";

function createContext(
  messages: Message[],
  lastHistoryTimestamp: Date | null,
): EventHandlerContext & { setMessagesCalls: () => number } {
  let setMessagesCalls = 0;

  return {
    sessionIdRef: { current: "session-1" },
    processedEventIdsRef: { current: new Set<string>() },
    lastHistoryTimestampRef: { current: lastHistoryTimestamp },
    activeSubagentStackRef: { current: [] },
    streamVersionRef: { current: 0 },
    setSessionId: () => undefined,
    setMessages: (updater: React.SetStateAction<Message[]>) => {
      setMessagesCalls += 1;
      if (typeof updater === "function") {
        updater(messages);
      }
    },
    setConnectionStatus: () => undefined,
    setIsInitializingSandbox: () => undefined,
    setSandboxError: () => undefined,
    setMessagesCalls: () => setMessagesCalls,
  };
}

test("skips replayed SSE events at the history timestamp boundary", () => {
  const timestamp = "2026-04-19T01:02:03.456Z";
  const ctx = createContext(
    [
      {
        id: "assistant-1",
        role: "assistant",
        content: "",
        timestamp: new Date(timestamp),
        parts: [],
        isStreaming: true,
      },
    ],
    new Date(timestamp),
  );

  const event: StreamEvent = {
    event: "message:chunk",
    data: JSON.stringify({ content: "duplicate", _timestamp: timestamp }),
  };

  handleStreamEvent(event, "assistant-1", "redis-event-1", timestamp, ctx);

  assert.equal(ctx.setMessagesCalls(), 0);
});

test("creates a new streaming assistant for a running run after the latest user message", () => {
  const messages: Message[] = [
    {
      id: "user-previous",
      role: "user",
      content: "previous question",
      timestamp: new Date("2026-04-19T01:00:00.000Z"),
      runId: "run-previous",
    },
    {
      id: "assistant-previous",
      role: "assistant",
      content: "previous answer",
      timestamp: new Date("2026-04-19T01:00:01.000Z"),
      runId: "run-previous",
      isStreaming: false,
    },
    {
      id: "user-latest",
      role: "user",
      content: "latest question",
      timestamp: new Date("2026-04-19T01:01:00.000Z"),
      runId: "run-latest",
    },
  ];

  const result = prepareMessagesForRunningRun(
    messages,
    "run-latest",
    () => "assistant-latest",
  );

  assert.equal(result.streamingMessageId, "assistant-latest");
  assert.deepEqual(
    result.messages.map((message) => [
      message.id,
      message.role,
      message.runId,
      message.isStreaming ?? false,
    ]),
    [
      ["user-previous", "user", "run-previous", false],
      ["assistant-previous", "assistant", "run-previous", false],
      ["user-latest", "user", "run-latest", false],
      ["assistant-latest", "assistant", "run-latest", true],
    ],
  );
});
