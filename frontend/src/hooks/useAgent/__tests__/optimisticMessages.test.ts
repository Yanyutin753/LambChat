import type { Message } from "../../../types";
import {
  createOptimisticMessagesForRetry,
  createOptimisticMessagesForSend,
} from "../optimisticMessages.ts";

test("normal optimistic send appends user and assistant messages", () => {
  const result = createOptimisticMessagesForSend({
    previousMessages: [],
    content: " hello ",
    now: new Date("2026-06-17T00:00:00.000Z"),
    createId: (() => {
      const ids = ["user-1", "assistant-1"];
      return () => ids.shift()!;
    })(),
  });

  expect(result.messages.map((message) => [message.id, message.role, message.content])).toEqual([
      ["user-1", "user", "hello"],
      ["assistant-1", "assistant", ""],
    ]);
  expect(result.assistantMessageId).toBe("assistant-1");
});

test("retry optimistic send replaces the cancelled assistant without adding a user", () => {
  const previousMessages = [
    {
      id: "user-1",
      role: "user",
      content: "retry this prompt",
      timestamp: new Date("2026-06-17T00:00:00.000Z"),
    },
    {
      id: "assistant-cancelled",
      role: "assistant",
      content: "",
      timestamp: new Date("2026-06-17T00:00:01.000Z"),
      cancelled: true,
      parts: [{ type: "cancelled" }],
    },
  ] satisfies Message[];

  const result = createOptimisticMessagesForRetry({
    previousMessages,
    assistantMessageId: "assistant-cancelled",
    now: new Date("2026-06-17T00:00:02.000Z"),
    createId: () => "assistant-retry",
  });

  expect(result.messages.map((message) => [message.id, message.role, message.content])).toEqual([
      ["user-1", "user", "retry this prompt"],
      ["assistant-retry", "assistant", ""],
    ]);
  expect(result.messages.filter((message) => message.role === "user").length).toBe(1);
  expect(result.messages[1]?.isStreaming).toBe(true);
  expect(result.messages[1]?.cancelled).toBe(undefined);
});

test("retry optimistic send inserts after the target user when the assistant is missing", () => {
  const previousMessages = [
    {
      id: "user-1",
      role: "user",
      content: "first",
      timestamp: new Date("2026-06-17T00:00:00.000Z"),
    },
    {
      id: "user-2",
      role: "user",
      content: "second",
      timestamp: new Date("2026-06-17T00:00:01.000Z"),
    },
  ] satisfies Message[];

  const result = createOptimisticMessagesForRetry({
    previousMessages,
    afterUserMessageId: "user-1",
    createId: () => "assistant-retry",
  });

  expect(result.messages.map((message) => message.id)).toEqual(["user-1", "assistant-retry", "user-2"]);
});
