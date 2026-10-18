import type { Message, PendingApproval } from "../../types";
import type { HistoryEvent } from "./types";
import { replayScheduledEvents } from "./scheduledEventReplay";
import { clearAllLoadingStates } from "./messageParts";
import { parseDate } from "../../utils/datetime";

export const SCHEDULED_PROGRESS_EVENT = "lambchat:scheduled-progress";
export const SCHEDULED_RESULT_EVENT = "lambchat:scheduled-result";
export const SCHEDULED_RESULTS_REFRESH_EVENT =
  "lambchat:scheduled-results-refresh";

export interface ScheduledResult {
  session_id: string;
  run_id: string;
  message_id: string;
  task_id: string;
  task_name: string;
  content: string;
  timestamp: string;
  execution_session_id?: string;
  events?: HistoryEvent[];
  assistant_identity?: Message["assistantIdentity"];
}

export interface ScheduledProgress extends ScheduledResult {
  status: "running" | "finishing" | "waiting_human" | "failed" | "quiet";
  approvals?: PendingApproval[];
  events_omitted?: boolean;
  updated_at: string;
}

function isScheduledPayload(
  value: unknown,
  allowEmptyContent = false,
): value is ScheduledResult {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  return (
    [
      "session_id",
      "run_id",
      "message_id",
      "task_id",
      "task_name",
      "content",
      "timestamp",
    ].every(
      (key) =>
        typeof data[key] === "string" &&
        (data[key] !== "" || (allowEmptyContent && key === "content")),
    ) &&
    Number.isFinite(Date.parse(data.timestamp as string)) &&
    (data.execution_session_id === undefined ||
      typeof data.execution_session_id === "string") &&
    (data.events === undefined ||
      (Array.isArray(data.events) &&
        data.events.every(
          (event) =>
            event &&
            typeof event === "object" &&
            typeof event.event_type === "string" &&
            event.data &&
            typeof event.data === "object" &&
            !Array.isArray(event.data),
        )))
  );
}

export function isScheduledResult(value: unknown): value is ScheduledResult {
  return isScheduledPayload(value);
}

export function isScheduledProgress(
  value: unknown,
): value is ScheduledProgress {
  if (!isScheduledPayload(value, true)) return false;
  const data = value as ScheduledProgress;
  return (
    ["running", "finishing", "waiting_human", "failed", "quiet"].includes(
      data.status,
    ) &&
    (data.approvals === undefined ||
      (Array.isArray(data.approvals) &&
        data.approvals.every(
          (approval) =>
            approval &&
            typeof approval.id === "string" &&
            typeof approval.message === "string" &&
            typeof approval.session_id === "string" &&
            Array.isArray(approval.fields),
        ))) &&
    typeof data.updated_at === "string" &&
    Number.isFinite(Date.parse(data.updated_at))
  );
}

export function mergeScheduledResult(
  messages: Message[],
  data: ScheduledResult,
): Message[] {
  const existingIndex = messages.findIndex(
    (message) => message.id === data.message_id,
  );
  const existing = messages[existingIndex];
  if (existing?.metadata?.scheduledFinal === true && !data.events)
    return messages;
  let result: Message = {
    id: data.message_id,
    role: "assistant",
    content: data.content,
    timestamp: existing?.timestamp ?? parseDate(data.timestamp),
    runId: data.run_id,
    isStreaming: false,
    assistantIdentity: data.assistant_identity ?? existing?.assistantIdentity,
    parts: [{ type: "text", content: data.content }],
    metadata: {
      scheduledTaskId: data.task_id,
      scheduledTaskName: data.task_name,
      scheduledFinal: true,
      scheduledExecutionSessionId:
        data.execution_session_id ??
        existing?.metadata?.scheduledExecutionSessionId ??
        `sch_conversation_${data.task_id}`,
      scheduledEventsLoaded: Boolean(data.events),
    },
  };
  const replay = data.events
    ? replayScheduledEvents(data.events, result)
    : existing;
  result = {
    ...result,
    tokenUsage: replay?.tokenUsage,
    duration: replay?.duration,
    assistantIdentity: replay?.assistantIdentity ?? result.assistantIdentity,
    parts: [
      ...clearAllLoadingStates(replay?.parts ?? []).filter(
        (part) => part.type !== "text" || part.depth,
      ),
      { type: "text", content: data.content },
    ],
  };
  if (existingIndex >= 0)
    return messages.map((message, index) =>
      index === existingIndex ? result : message,
    );
  const index = messages.findIndex(
    (message) => message.timestamp > result.timestamp,
  );
  return index < 0
    ? [...messages, result]
    : [...messages.slice(0, index), result, ...messages.slice(index)];
}

export function mergeScheduledProgress(
  messages: Message[],
  data: ScheduledProgress,
): Message[] {
  const index = messages.findIndex((message) => message.id === data.message_id);
  const existing = messages[index];
  if (existing?.metadata?.scheduledFinal === true) return messages;
  const previousUpdate = existing?.metadata?.scheduledUpdatedAt;
  if (typeof previousUpdate === "string") {
    const previousTime = Date.parse(previousUpdate);
    const nextTime = Date.parse(data.updated_at);
    if (
      previousTime > nextTime ||
      (previousTime === nextTime &&
        (!data.events ||
          data.events.length <=
            Number(existing?.metadata?.scheduledEventCount ?? 0)))
    )
      return messages;
  }
  if (data.status === "quiet")
    return index < 0
      ? messages
      : messages.filter((message) => message.id !== data.message_id);
  const events = data.events?.length ? data.events : undefined;
  const content = data.content || (!events ? existing?.content : "") || "";
  let message: Message = {
    ...existing,
    id: data.message_id,
    role: "assistant",
    content,
    timestamp: existing?.timestamp ?? parseDate(data.timestamp),
    runId: data.run_id,
    isStreaming: data.status === "running" || data.status === "finishing",
    assistantIdentity: data.assistant_identity ?? existing?.assistantIdentity,
    parts: [
      ...(!events ? existing?.parts ?? [] : []).filter(
        (part) => part.type !== "text" || part.depth,
      ),
      ...(content ? [{ type: "text" as const, content }] : []),
    ],
    metadata: {
      ...existing?.metadata,
      scheduledTaskId: data.task_id,
      scheduledTaskName: data.task_name,
      scheduledProgressStatus: data.status,
      scheduledUpdatedAt: data.updated_at,
      scheduledExecutionSessionId:
        data.execution_session_id ??
        existing?.metadata?.scheduledExecutionSessionId,
      scheduledEventCount:
        events?.length ?? existing?.metadata?.scheduledEventCount ?? 0,
    },
  };
  if (events) message = replayScheduledEvents(events, message);
  else if (!message.isStreaming && data.status !== "waiting_human") {
    message.parts = clearAllLoadingStates(message.parts ?? []);
  }
  if (index >= 0)
    return messages.map((previous, at) => (at === index ? message : previous));
  const before = messages.findIndex(
    (previous) => previous.timestamp > message.timestamp,
  );
  return before < 0
    ? [...messages, message]
    : [...messages.slice(0, before), message, ...messages.slice(before)];
}
