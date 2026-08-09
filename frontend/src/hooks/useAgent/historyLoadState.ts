import type { Feedback, Message } from "../../types";

export function resolveHistoryStreamRunId(
  streamRunId: string | null | undefined,
  targetRunId?: string,
): string | null {
  if (!streamRunId) return null;
  return targetRunId && targetRunId !== streamRunId ? null : streamRunId;
}

export function applyFeedbackToMessages(
  messages: Message[],
  items: Feedback[],
): Message[] {
  const byRun = new Map(items.map((item) => [item.run_id, item]));
  let changed = false;
  const next = messages.map((message) => {
    const feedback = message.runId ? byRun.get(message.runId) : undefined;
    if (!feedback) return message;
    changed = true;
    return {
      ...message,
      feedback: feedback.rating,
      feedbackId: feedback.id,
    };
  });
  return changed ? next : messages;
}
