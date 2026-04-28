import assert from "node:assert/strict";
import test from "node:test";
import type { Message } from "../../types";
import { handleStreamEvent } from "./eventHandlers.ts";
import type { EventHandlerContext } from "./eventHandlers.ts";
import type { StreamEvent } from "./types.ts";

function createContext(messages: Message[]): {
  ctx: EventHandlerContext;
  getMessages: () => Message[];
} {
  let currentMessages = messages;

  return {
    ctx: {
      sessionIdRef: { current: "session-1" },
      processedEventIdsRef: { current: new Set<string>() },
      lastHistoryTimestampRef: { current: null },
      activeSubagentStackRef: { current: [] },
      streamVersionRef: { current: 0 },
      setSessionId: () => undefined,
      setMessages: (updater: React.SetStateAction<Message[]>) => {
        currentMessages =
          typeof updater === "function" ? updater(currentMessages) : updater;
      },
      setConnectionStatus: () => undefined,
      setIsInitializingSandbox: () => undefined,
      setSandboxError: () => undefined,
    },
    getMessages: () => currentMessages,
  };
}

test("replaces the optimistic user message when the backend adds a timestamp prefix", () => {
  const { ctx, getMessages } = createContext([
    {
      id: "user-1",
      role: "user",
      content: "hello world",
      timestamp: new Date("2026-04-28T12:00:00.000Z"),
    },
    {
      id: "assistant-1",
      role: "assistant",
      content: "",
      timestamp: new Date("2026-04-28T12:00:00.000Z"),
      isStreaming: true,
      parts: [],
    },
  ]);

  const event: StreamEvent = {
    event: "user:message",
    data: JSON.stringify({
      content: "[2026-04-28 20:00:00 +08:00 Asia/Shanghai] hello world",
      attachments: [],
    }),
  };

  handleStreamEvent(
    event,
    "assistant-1",
    "redis-event-1",
    "2026-04-28T12:00:01.000Z",
    ctx,
  );

  const messages = getMessages();
  assert.equal(messages.length, 2);
  assert.equal(
    messages[0]?.content,
    "[2026-04-28 20:00:00 +08:00 Asia/Shanghai] hello world",
  );
});
