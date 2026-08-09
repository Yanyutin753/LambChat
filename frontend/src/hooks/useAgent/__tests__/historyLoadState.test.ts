import type { Feedback, Message } from "../../../types";
import {
  applyFeedbackToMessages,
  resolveHistoryStreamRunId,
} from "../historyLoadState.ts";

test("resolveHistoryStreamRunId only reconnects the selected current run", () => {
  expect(resolveHistoryStreamRunId("run-current", undefined)).toBe(
    "run-current",
  );
  expect(resolveHistoryStreamRunId("run-current", "run-current")).toBe(
    "run-current",
  );
  expect(resolveHistoryStreamRunId("run-current", "run-old")).toBeNull();
  expect(resolveHistoryStreamRunId(null, undefined)).toBeNull();
});

test("applyFeedbackToMessages updates matching runs and preserves unrelated identity", () => {
  const matching: Message = {
    id: "assistant-current",
    role: "assistant",
    content: "answer",
    timestamp: new Date("2026-08-09T00:00:00.000Z"),
    runId: "run-current",
  };
  const unrelated: Message = {
    id: "assistant-old",
    role: "assistant",
    content: "old answer",
    timestamp: new Date("2026-08-08T00:00:00.000Z"),
    runId: "run-old",
  };
  const feedback = {
    id: "feedback-1",
    run_id: "run-current",
    rating: "up",
  } as Feedback;

  const result = applyFeedbackToMessages([matching, unrelated], [feedback]);

  expect(result[0]).toEqual({
    ...matching,
    feedback: "up",
    feedbackId: "feedback-1",
  });
  expect(result[1]).toBe(unrelated);
});

test("applyFeedbackToMessages preserves the array when nothing matches", () => {
  const messages: Message[] = [
    {
      id: "assistant-old",
      role: "assistant",
      content: "old answer",
      timestamp: new Date("2026-08-08T00:00:00.000Z"),
      runId: "run-old",
    },
  ];

  expect(applyFeedbackToMessages(messages, [])).toBe(messages);
});
