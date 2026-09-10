import type { Message } from "../../../types";
import {
  assistantMessageHasContent,
  settleAssistantMessage,
} from "../settleStream.ts";

function assistant(overrides: Partial<Message> = {}): Message {
  return {
    id: "assistant-1",
    role: "assistant",
    content: "",
    timestamp: new Date("2026-09-10T03:00:00.000Z"),
    parts: [],
    isStreaming: true,
    ...overrides,
  };
}

function user(): Message {
  return {
    id: "run-1:user",
    role: "user",
    content: "hello",
    timestamp: new Date("2026-09-10T02:59:59.000Z"),
  };
}

test("assistantMessageHasContent treats recommend-only parts as empty", () => {
  expect(assistantMessageHasContent(assistant())).toBe(false);
  expect(
    assistantMessageHasContent(
      assistant({
        parts: [
          {
            type: "recommend_questions",
            questions: [{ content: "next?" }],
          },
        ],
      }),
    ),
  ).toBe(false);
  expect(assistantMessageHasContent(assistant({ content: "answer" }))).toBe(
    true,
  );
  expect(assistantMessageHasContent(assistant({ cancelled: true }))).toBe(true);
});

test("settling an empty streaming assistant removes the orphan bubble", () => {
  const settled = settleAssistantMessage([user(), assistant()], "assistant-1");

  expect(settled).toHaveLength(1);
  expect(settled[0]?.role).toBe("user");
});

test("settling a recommend-only shell removes it", () => {
  const settled = settleAssistantMessage(
    [
      user(),
      assistant({
        parts: [
          {
            type: "recommend_questions",
            questions: [{ content: "next?" }],
          },
        ],
      }),
    ],
    "assistant-1",
  );

  expect(settled).toHaveLength(1);
  expect(settled[0]?.role).toBe("user");
});

test("settling keeps a content-bearing assistant and stops streaming", () => {
  const settled = settleAssistantMessage(
    [user(), assistant({ content: "final answer" })],
    "assistant-1",
  );

  expect(settled).toHaveLength(2);
  expect(settled[1]?.isStreaming).toBe(false);
  expect(settled[1]?.content).toBe("final answer");
});

test("settling keeps a turn whose only part is a pending ask_human card", () => {
  const settled = settleAssistantMessage(
    [
      user(),
      assistant({
        parts: [
          {
            type: "tool",
            name: "ask_human",
            id: "approval-1",
            args: { message: "confirm?" },
            isPending: true,
          },
        ],
      }),
    ],
    "assistant-1",
  );

  expect(settled).toHaveLength(2);
  expect(settled[1]?.parts?.[0]?.type).toBe("tool");
});

test("settling is a no-op when the target message is absent", () => {
  const settled = settleAssistantMessage([user()], "assistant-1");

  expect(settled).toHaveLength(1);
});
