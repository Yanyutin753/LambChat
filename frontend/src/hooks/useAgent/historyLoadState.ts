import type { Feedback, Message } from "../../types";

/** Independent scheduled results can arrive after a history request's snapshot. */
export function preserveScheduledMessages(
  messages: Message[],
  current: Message[],
): Message[] {
  const live = new Map<string, Message>();
  for (const message of current) {
    if (
      message.metadata?.scheduledTaskId &&
      (!live.get(message.id)?.metadata?.scheduledFinal ||
        message.metadata.scheduledFinal)
    ) {
      live.set(message.id, message);
    }
  }
  let changed = false;
  const next = messages.map((message) => {
    const latest = live.get(message.id);
    if (
      latest &&
      (latest.metadata?.scheduledFinal === true ||
        (message.metadata?.scheduledFinal !== true &&
          Date.parse(String(latest.metadata?.scheduledUpdatedAt)) >
            Date.parse(
              String(message.metadata?.scheduledUpdatedAt || "1970-01-01"),
            )))
    ) {
      changed = true;
      return latest;
    }
    return message;
  });
  const ids = new Set(messages.map((message) => message.id));
  const additions = [...live.values()].filter(
    (message) => !ids.has(message.id),
  );
  return changed || additions.length
    ? [...next, ...additions].sort(
        (a, b) => a.timestamp.getTime() - b.timestamp.getTime(),
      )
    : messages;
}

export function resolveHistoryStreamRunId(
  streamRunId: string | null | undefined,
  targetRunId?: string,
  goal?: { status: string; current_run_id?: string | null } | null,
): string | null {
  // A reserved continuation can precede its running history trace.
  if (goal?.status === "active" && goal.current_run_id) {
    streamRunId = goal.current_run_id;
  }
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
