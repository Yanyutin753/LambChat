import type { Message } from "../../../types";
import { handleStreamEvent } from "../eventHandlers.ts";
import type { EventHandlerContext } from "../eventHandlers.ts";
import type { StreamEvent } from "../types.ts";

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
    setIsRecallingMemory: () => undefined,
      setSandboxError: () => undefined,
      setActiveGoal: () => undefined,
      setGoalsByRunId: () => undefined,
    },
    getMessages: () => currentMessages,
  };
}

test("keeps the streaming assistant under the newest user message when resending identical content", () => {
  const { ctx, getMessages } = createContext([
    {
      id: "uuid-a",
      role: "user",
      content: "帮我写个 haiku",
      timestamp: new Date("2026-08-26T10:00:00.000Z"),
      runId: "run-1",
    },
    {
      id: "run-1",
      role: "assistant",
      content: "好的，这是一首诗…",
      timestamp: new Date("2026-08-26T10:00:05.000Z"),
      parts: [],
      isStreaming: false,
    },
    {
      id: "uuid-b",
      role: "user",
      content: "帮我写个 haiku",
      timestamp: new Date("2026-08-26T11:00:00.000Z"),
    },
    {
      id: "run-2",
      role: "assistant",
      content: "",
      timestamp: new Date("2026-08-26T11:00:00.000Z"),
      parts: [],
      isStreaming: true,
      runId: "run-2",
    },
  ]);

  handleStreamEvent(
    {
      event: "user:message",
      data: JSON.stringify({
        content: "帮我写个 haiku",
        message_id: "run-2:user",
        run_id: "run-2",
      }),
    },
    "run-2",
    "redis-event-2",
    "2026-08-26T11:00:01.000Z",
    ctx,
  );

  const messages = getMessages();
  expect(messages.map((m) => `${m.role}:${m.id}`)).toEqual([
    "user:uuid-a",
    "assistant:run-1",
    "user:uuid-b",
    "assistant:run-2",
  ]);
  expect(messages[0]?.runId).toBe("run-1");
  expect(messages[2]?.runId).toBe("run-2");
});

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
  expect(messages.length).toBe(2);
  expect(messages[0]?.content).toBe(
    "[2026-04-28 20:00:00 +08:00 Asia/Shanghai] hello world",
  );
});
