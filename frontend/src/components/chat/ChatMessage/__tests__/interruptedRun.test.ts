import { describe, expect, test } from "vitest";
import { isInterruptedRunMessage } from "../interruptedRun";
import type { Message, MessagePart } from "../../../types";

function assistantMessage(parts: MessagePart[], overrides: Partial<Message> = {}): Message {
  return {
    id: "m1",
    role: "assistant",
    content: "",
    timestamp: new Date("2026-10-03T12:00:00Z"),
    isStreaming: false,
    parts,
    ...overrides,
  } as Message;
}

const subagentPart: MessagePart = {
  type: "subagent",
  name: "ArXiv前沿论文猎手",
  status: "completed",
  parts: [],
} as unknown as MessagePart;

const textPart: MessagePart = { type: "text", content: "结果如下" };
const recommendPart: MessagePart = {
  type: "recommend_questions",
  questions: [{ content: "继续？" }],
};
const cancelledPart: MessagePart = { type: "cancelled" };
const askHumanPart: MessagePart = {
  type: "tool",
  name: "ask_human",
  isPending: true,
} as unknown as MessagePart;

describe("isInterruptedRunMessage", () => {
  test("run that only left process parts and no output is interrupted", () => {
    expect(isInterruptedRunMessage(assistantMessage([subagentPart]))).toBe(true);
  });

  test("run with final text output is not interrupted", () => {
    expect(
      isInterruptedRunMessage(assistantMessage([subagentPart, textPart])),
    ).toBe(false);
  });

  test("legacy content-only message with output is not interrupted", () => {
    expect(
      isInterruptedRunMessage(
        assistantMessage([subagentPart], { content: "结果如下" }),
      ),
    ).toBe(false);
  });

  test("streaming messages are never interrupted", () => {
    expect(
      isInterruptedRunMessage(
        assistantMessage([subagentPart], { isStreaming: true }),
      ),
    ).toBe(false);
  });

  test("user-stopped runs are handled by the cancelled UI, not this banner", () => {
    expect(
      isInterruptedRunMessage(
        assistantMessage([subagentPart], { cancelled: true }),
      ),
    ).toBe(false);
    expect(
      isInterruptedRunMessage(assistantMessage([subagentPart, cancelledPart])),
    ).toBe(false);
  });

  test("runs waiting for human input are not interrupted", () => {
    expect(
      isInterruptedRunMessage(assistantMessage([subagentPart, askHumanPart])),
    ).toBe(false);
  });

  test("recommend-questions-only turns are not interrupted", () => {
    expect(
      isInterruptedRunMessage(assistantMessage([recommendPart])),
    ).toBe(false);
    expect(
      isInterruptedRunMessage(assistantMessage([recommendPart, subagentPart])),
    ).toBe(true);
  });

  test("messages without any run trace never show the banner", () => {
    expect(isInterruptedRunMessage(assistantMessage([]))).toBe(false);
    expect(
      isInterruptedRunMessage(assistantMessage([], { content: "" })),
    ).toBe(false);
  });
});
