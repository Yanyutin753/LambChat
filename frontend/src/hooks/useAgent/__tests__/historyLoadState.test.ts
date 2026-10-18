import type { Feedback, Message } from "../../../types";
import {
  applyFeedbackToMessages,
  preserveScheduledMessages,
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

test("history replacement preserves only missing independent scheduled results in timestamp order", () => {
  const message = (id: string, time: number, scheduled = false): Message => ({
    id,
    role: "assistant",
    content: id,
    timestamp: new Date(time),
    ...(scheduled ? { metadata: { scheduledTaskId: "task" } } : {}),
  });
  const incoming = [
    message("older", 1),
    message("persisted-result", 3, true),
    message("newer", 5),
  ];
  const late = message("late-result", 4, true);
  const merged = preserveScheduledMessages(incoming, [
    message("stale-text", 2),
    message("persisted-result", 3, true),
    late,
    late,
  ]);
  expect(merged.map((value) => value.id)).toEqual([
    "older",
    "persisted-result",
    "late-result",
    "newer",
  ]);
  expect(merged[2]).toBe(late);
});

test("a stale scheduled progress snapshot cannot replace a same-ID final result", () => {
  const progress: Message = {
    id: "scheduled-result:run",
    role: "assistant",
    content: "working",
    timestamp: new Date(1),
    isStreaming: true,
    metadata: {
      scheduledTaskId: "task",
      scheduledUpdatedAt: "2026-10-17T00:00:01Z",
    },
  };
  const final: Message = {
    ...progress,
    content: "finished",
    isStreaming: false,
    metadata: { ...progress.metadata, scheduledFinal: true },
  };
  expect(preserveScheduledMessages([progress], [progress, final])).toEqual([
    final,
  ]);
  expect(preserveScheduledMessages([progress], [final])[0]).toBe(final);
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

test("a reserved Goal turn streams even before its history trace is visible", () => {
  const goal = { status: "active", current_run_id: "goal-next" } as const;
  expect(resolveHistoryStreamRunId(null, "goal-next", goal)).toBe("goal-next");
  expect(resolveHistoryStreamRunId("goal-old", undefined, goal)).toBe(
    "goal-next",
  );
  expect(resolveHistoryStreamRunId("goal-old", "goal-old", goal)).toBeNull();
  expect(
    resolveHistoryStreamRunId(null, undefined, { ...goal, status: "paused" }),
  ).toBeNull();
});
