import assert from "node:assert/strict";
import test from "node:test";
import { findCancelledRetryTarget } from "../cancelledRetry.ts";
import type { Message } from "../../../../types";

test("finds the closest user message before a cancelled assistant message", () => {
  const messages = [
    {
      id: "user-1",
      role: "user",
      content: "old prompt",
      timestamp: new Date("2026-05-30T00:00:00.000Z"),
    },
    {
      id: "assistant-1",
      role: "assistant",
      content: "old answer",
      timestamp: new Date("2026-05-30T00:00:01.000Z"),
    },
    {
      id: "user-2",
      role: "user",
      content: "  retry this prompt  ",
      timestamp: new Date("2026-05-30T00:00:02.000Z"),
      attachments: [
        {
          id: "attachment-1",
          key: "uploads/file.txt",
          name: "file.txt",
          type: "document",
          mimeType: "text/plain",
          size: 12,
          url: "/uploads/file.txt",
        },
      ],
    },
    {
      id: "assistant-cancelled",
      role: "assistant",
      content: "",
      timestamp: new Date("2026-05-30T00:00:03.000Z"),
      cancelled: true,
      parts: [{ type: "cancelled" }],
    },
  ] satisfies Message[];

  assert.deepEqual(findCancelledRetryTarget(messages, "assistant-cancelled"), {
    userMessageId: "user-2",
    assistantMessageId: "assistant-cancelled",
    content: "retry this prompt",
    attachments: messages[2]?.attachments,
  });
});

test("returns null when there is no user message to replay", () => {
  const messages = [
    {
      id: "assistant-cancelled",
      role: "assistant",
      content: "",
      timestamp: new Date("2026-05-30T00:00:03.000Z"),
      cancelled: true,
      parts: [{ type: "cancelled" }],
    },
  ] satisfies Message[];

  assert.equal(findCancelledRetryTarget(messages, "assistant-cancelled"), null);
});
