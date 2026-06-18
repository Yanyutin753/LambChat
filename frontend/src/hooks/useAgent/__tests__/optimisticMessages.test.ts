import assert from "node:assert/strict";
import test from "node:test";
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

  assert.deepEqual(
    result.messages.map((message) => [message.id, message.role, message.content]),
    [
      ["user-1", "user", "hello"],
      ["assistant-1", "assistant", ""],
    ],
  );
  assert.equal(result.assistantMessageId, "assistant-1");
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

  assert.deepEqual(
    result.messages.map((message) => [message.id, message.role, message.content]),
    [
      ["user-1", "user", "retry this prompt"],
      ["assistant-retry", "assistant", ""],
    ],
  );
  assert.equal(result.messages.filter((message) => message.role === "user").length, 1);
  assert.equal(result.messages[1]?.isStreaming, true);
  assert.equal(result.messages[1]?.cancelled, undefined);
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

  assert.deepEqual(
    result.messages.map((message) => message.id),
    ["user-1", "assistant-retry", "user-2"],
  );
});
