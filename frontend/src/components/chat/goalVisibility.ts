import type { PersistentGoal } from "../../services/api/session";
import type { Message } from "../../types";
import type { ActiveGoalSpec } from "../../hooks/useAgent/types";

function messageMatchesGoalRun(
  goal: ActiveGoalSpec,
  message: Pick<Message, "runId">,
): boolean {
  return Boolean(goal.runId && message.runId && goal.runId === message.runId);
}

export function getVisibleActiveGoalForMessages(
  goal: ActiveGoalSpec | null,
  messages: Pick<Message, "runId">[],
): ActiveGoalSpec | null {
  if (!goal || messages.length === 0) return null;
  if (!goal.runId) return goal;
  const latestMessage = messages[messages.length - 1];
  return latestMessage && messageMatchesGoalRun(goal, latestMessage)
    ? goal
    : null;
}

export function getGoalForMessage(
  goalsByRunId: Record<string, ActiveGoalSpec>,
  message: Pick<Message, "runId">,
): ActiveGoalSpec | null {
  return message.runId ? goalsByRunId[message.runId] ?? null : null;
}

export function shouldShowGoalDetailsForMessage(
  goal: ActiveGoalSpec | null | undefined,
  message: Pick<Message, "timestamp" | "runId">,
): boolean {
  if (!goal?.started_at || !message.timestamp) return false;
  if (goal.runId || message.runId) return messageMatchesGoalRun(goal, message);
  return new Date(message.timestamp) >= new Date(goal.started_at);
}

export function hasVisiblePersistentGoal(
  goal: Pick<PersistentGoal, "status"> | null | undefined,
): boolean {
  return Boolean(goal && !["cleared", "completed"].includes(goal.status));
}
