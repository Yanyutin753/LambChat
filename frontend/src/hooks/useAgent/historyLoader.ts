/**
 * History event loader for useAgent hook
 * Reconstructs messages from stored events.
 *
 * Message transformation logic is unified in processMessageEvent (messageParts.ts).
 * This file handles: event iteration, message reconstruction, and
 * user:message / user:cancel / approval_required which are history-specific.
 */

import type { Message, MessagePart, FormField } from "../../types";
import { uuid } from "../../utils/uuid";
import { authFetch } from "../../services/api/fetch";
import { buildApiUrl } from "../../services/api/config";
import i18n from "../../i18n";
import type {
  EventData,
  SubagentStackItem,
  HistoryEvent,
  HistoryEventData,
  ActiveGoalSpec,
} from "./types";
import { convertAttachments, processMessageEvent } from "./eventProcessor";
import { clearAllLoadingStates } from "./messageParts";
import { parseDate } from "../../utils/datetime";

function resolveUserMessageId(
  event: HistoryEvent,
  eventData: HistoryEventData,
): string {
  if (typeof eventData.message_id === "string" && eventData.message_id.trim()) {
    return eventData.message_id;
  }
  if (typeof event.run_id === "string" && event.run_id.trim()) {
    return `${event.run_id}:user`;
  }
  return uuid();
}

interface ProcessHistoryOptions {
  options?: {
    onApprovalRequired?: (approval: {
      id: string;
      message: string;
      type: string;
      fields?: FormField[];
      metadata?: Record<string, unknown>;
    }) => void;
  };
  activeSubagentStack: SubagentStackItem[];
}

function parseEventTimestamp(
  timestamp: string | undefined,
  fallbackMs: number,
): Date {
  return timestamp ? parseDate(timestamp) : new Date(fallbackMs);
}

function canAttachEventTypeToPreviousAssistant(eventType: string): boolean {
  return (
    eventType !== "user:message" &&
    eventType !== "user:cancel" &&
    eventType !== "metadata" &&
    eventType !== "done" &&
    eventType !== "goal:updated" &&
    eventType !== "approval_required"
  );
}

function canAttachToPreviousAssistant(
  event: HistoryEvent,
  message: Message | undefined,
): message is Message {
  return (
    message?.role === "assistant" &&
    Boolean(event.run_id) &&
    message.runId === event.run_id
  );
}

function shouldReplaceCancelledAssistantWithRetry(
  event: HistoryEvent,
  message: Message | undefined,
): boolean {
  return (
    canAttachEventTypeToPreviousAssistant(event.event_type) &&
    message?.role === "assistant" &&
    message.cancelled === true &&
    Boolean(event.run_id) &&
    message.runId !== event.run_id
  );
}

/**
 * Process a single history event and update message state.
 * Returns updated currentAssistantMessage or new message.
 */
function processHistoryEvent(
  event: HistoryEvent,
  currentAssistantMessage: Message | null,
  processedEventIds: Set<string>,
  opts: ProcessHistoryOptions,
): Message | null {
  const eventType = event.event_type;
  const eventData = event.data as HistoryEventData;
  const depth = eventData.depth || 0;
  const agentId = eventData.agent_id;

  // Track processed event IDs
  if (event.id) {
    processedEventIds.add(event.id.toString());
  }

  // Handle user message
  if (eventType === "user:message") {
    return null; // Signal to push current assistant and create user message
  }

  // Skip events that don't contribute to message content
  if (
    eventType === "metadata" ||
    eventType === "done" ||
    eventType === "goal:updated"
  ) {
    return currentAssistantMessage;
  }

  // Handle approval_required
  if (eventType === "approval_required") {
    const approvalData = eventData as {
      id?: string;
      message?: string;
      type?: string;
      fields?: FormField[];
    };
    if (approvalData.id && opts.options?.onApprovalRequired) {
      authFetch<{
        status: string;
        message?: string;
        type?: string;
        fields?: FormField[];
        metadata?: Record<string, unknown>;
      }>(buildApiUrl(`/human/${approvalData.id}`))
        .then((data) => data ?? null)
        .then((approval) => {
          if (approval?.status === "pending") {
            opts.options?.onApprovalRequired?.({
              id: approvalData.id!,
              message: approval.message || "",
              type: approval.type || "form",
              fields: approval.fields,
              metadata: approval.metadata,
            });
          }
        })
        .catch((e) => {
          console.warn("[loadHistory] Failed to check approval status:", e);
        });
    }
    return currentAssistantMessage;
  }

  // CancelledError with no current message — don't create an empty assistant message
  if (eventType === "error") {
    const errorData = eventData as { type?: string };
    if (errorData.type === "CancelledError" && !currentAssistantMessage) {
      return null;
    }
  }

  // Ensure assistant message exists for other event types
  let msg = currentAssistantMessage;
  if (!msg) {
    const messageId = event.run_id || uuid();
    msg = {
      id: messageId,
      role: "assistant",
      content: "",
      timestamp: parseEventTimestamp(event.timestamp, Date.now()),
      parts: [],
      isStreaming: false,
      runId: event.run_id,
    };
  } else if (event.run_id && !msg.runId) {
    msg = { ...msg, runId: event.run_id };
  }

  // Manage subagent stack
  if (eventType === "agent:call") {
    opts.activeSubagentStack.push({
      agent_id: agentId || "unknown",
      depth,
      message_id: msg.id,
    });
  }

  // Use unified event processor
  const result = processMessageEvent(
    eventType,
    eventData as EventData,
    msg.parts || [],
    msg.content,
    msg.toolCalls || [],
    depth,
    opts.activeSubagentStack,
    false, // isStreaming = false for history
    msg.id,
  );

  // Apply result to message
  msg.parts = result.parts;
  msg.content = result.content;
  msg.toolCalls = result.toolCalls;

  if (result.toolResult) {
    msg.toolResults = [...(msg.toolResults || []), result.toolResult];
  }
  if (result.tokenUsage) {
    msg.tokenUsage = result.tokenUsage;
  }
  if (result.duration) {
    msg.duration = result.duration;
  }
  if (result.cancelled) {
    msg.cancelled = true;
  }

  // Pop subagent stack after agent:result
  if (eventType === "agent:result") {
    const stackIndex = opts.activeSubagentStack.findIndex(
      (item) =>
        item.agent_id === (agentId || "unknown") && item.message_id === msg.id,
    );
    if (stackIndex !== -1) {
      opts.activeSubagentStack.splice(stackIndex, 1);
    }
  }

  return msg;
}

/**
 * Reconstruct messages from history events.
 */
export function reconstructMessagesFromEvents(
  events: HistoryEvent[],
  processedEventIds: Set<string>,
  opts: ProcessHistoryOptions,
): Message[] {
  // Sort events by timestamp
  const sortedEvents = [...events].sort((a, b) => {
    const timeA = parseEventTimestamp(a.timestamp, 0).getTime();
    const timeB = parseEventTimestamp(b.timestamp, 0).getTime();
    return timeA - timeB;
  });

  const reconstructedMessages: Message[] = [];
  let currentAssistantMessage: Message | null = null;
  const seenUserMessageIds = new Set<string>();
  const seenUserMessageRunIds = new Set<string>();

  for (const event of sortedEvents) {
    const eventType = event.event_type;
    const eventData = event.data as HistoryEventData;

    // Handle user message separately
    if (eventType === "user:message") {
      const userMessageId = resolveUserMessageId(event, eventData);
      const userMessageRunId =
        typeof event.run_id === "string" && event.run_id.trim()
          ? event.run_id
          : null;
      if (
        seenUserMessageIds.has(userMessageId) ||
        (userMessageRunId && seenUserMessageRunIds.has(userMessageRunId))
      ) {
        continue;
      }
      seenUserMessageIds.add(userMessageId);
      if (userMessageRunId) {
        seenUserMessageRunIds.add(userMessageRunId);
      }

      if (currentAssistantMessage) {
        reconstructedMessages.push(currentAssistantMessage);
        currentAssistantMessage = null;
      }
      const userAttachments = convertAttachments(eventData.attachments);
      reconstructedMessages.push({
        id: userMessageId,
        role: "user",
        content: eventData.content || "",
        timestamp: parseEventTimestamp(event.timestamp, Date.now()),
        attachments: userAttachments,
        runId: event.run_id,
      });
      continue;
    }

    // Handle user cancel
    if (eventType === "user:cancel") {
      if (currentAssistantMessage) {
        const clearedParts = clearAllLoadingStates(
          currentAssistantMessage.parts || [],
        );
        // Also set result on pending tools for history display
        const updatedParts = clearedParts.map((part): MessagePart => {
          if (part.type === "tool" && part.cancelled && !part.result) {
            return {
              ...part,
              result: i18n.t("chat.cancelled"),
              success: false,
            };
          }
          return part;
        });
        const updatedMessage = {
          ...currentAssistantMessage,
          isStreaming: false,
          cancelled: true,
          parts: [...updatedParts, { type: "cancelled" as const }],
        };
        reconstructedMessages.push(updatedMessage);
      } else {
        reconstructedMessages.push({
          id: uuid(),
          role: "assistant",
          content: "",
          timestamp: parseEventTimestamp(event.timestamp, Date.now()),
          parts: [{ type: "cancelled" }],
          runId: event.run_id,
        });
      }
      currentAssistantMessage = null;
      continue;
    }

    if (
      !currentAssistantMessage &&
      canAttachEventTypeToPreviousAssistant(eventType)
    ) {
      const lastMessageIndex = reconstructedMessages.length - 1;
      const lastMessage = reconstructedMessages[lastMessageIndex];
      if (shouldReplaceCancelledAssistantWithRetry(event, lastMessage)) {
        currentAssistantMessage = processHistoryEvent(
          event,
          null,
          processedEventIds,
          opts,
        );
        reconstructedMessages.splice(lastMessageIndex, 1);
        continue;
      }
      if (canAttachToPreviousAssistant(event, lastMessage)) {
        const updatedMessage = processHistoryEvent(
          event,
          lastMessage,
          processedEventIds,
          opts,
        );
        if (updatedMessage) {
          reconstructedMessages[lastMessageIndex] = updatedMessage;
        }
        continue;
      }
    }

    // Process other events
    currentAssistantMessage = processHistoryEvent(
      event,
      currentAssistantMessage,
      processedEventIds,
      opts,
    );
  }

  if (currentAssistantMessage) {
    reconstructedMessages.push(currentAssistantMessage);
  }

  return reconstructedMessages;
}

export interface RunningAssistantPreparationResult {
  messages: Message[];
  streamingMessageId: string;
}

function getPendingOptimisticUserForRun(
  currentMessages: Message[],
  runId: string,
): Message | null {
  const streamingAssistantIndex = currentMessages.findIndex(
    (message) =>
      message.role === "assistant" &&
      message.isStreaming &&
      (message.runId === runId || message.id === runId),
  );
  if (streamingAssistantIndex <= 0) {
    return null;
  }

  const candidate = currentMessages[streamingAssistantIndex - 1];
  if (candidate?.role !== "user") {
    return null;
  }

  return {
    ...candidate,
    runId: candidate.runId ?? runId,
  };
}

export function prepareMessagesForRunningRun(
  messages: Message[],
  runId: string,
  createId: () => string = () => uuid(),
  currentMessages: Message[] = [],
): RunningAssistantPreparationResult {
  const pendingOptimisticUser = getPendingOptimisticUserForRun(
    currentMessages,
    runId,
  );
  const messagesWithPendingUser =
    pendingOptimisticUser &&
    !messages.some(
      (message) => message.role === "user" && message.runId === runId,
    )
      ? [...messages, pendingOptimisticUser]
      : messages;

  const existingAssistant = [...messagesWithPendingUser]
    .reverse()
    .find((message) => message.role === "assistant" && message.runId === runId);

  if (existingAssistant) {
    return {
      streamingMessageId: existingAssistant.id,
      messages: messagesWithPendingUser.map((message) =>
        message.id === existingAssistant.id
          ? { ...message, isStreaming: true }
          : message,
      ),
    };
  }

  const streamingMessageId = createId();
  return {
    streamingMessageId,
    messages: [
      ...messagesWithPendingUser,
      {
        id: streamingMessageId,
        role: "assistant",
        content: "",
        timestamp: new Date(),
        parts: [],
        isStreaming: true,
        runId,
      },
    ],
  };
}

/**
 * Get the last event timestamp from sorted events.
 */
export function getLastEventTimestamp(events: HistoryEvent[]): Date | null {
  if (events.length === 0) return null;
  let lastEvent: HistoryEvent | null = null;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].timestamp) {
      lastEvent = events[i];
      break;
    }
  }
  return lastEvent?.timestamp ? parseDate(lastEvent.timestamp) : null;
}

/**
 * Extract the latest active goal from history events.
 *
 * Scans for the most recent `goal:start` / `goal:end` pair and reconstructs
 * an `ActiveGoalSpec` so the UI can show the goal indicator after a page
 * reload or session switch.
 */
export function extractGoalFromEvents(
  events: HistoryEvent[],
): ActiveGoalSpec | null {
  let goal: ActiveGoalSpec | null = null;

  for (const event of events) {
    const eventType = event.event_type;
    if (eventType !== "goal:start" && eventType !== "goal:end") continue;

    const data = event.data as Record<string, unknown> | null | undefined;
    if (!data) continue;

    const goalData = data.goal as Record<string, unknown> | undefined;
    const existing: ActiveGoalSpec = goal ?? {
      objective: "",
    };

    const next: ActiveGoalSpec = {
      objective: (goalData?.objective as string) ?? existing.objective ?? "",
      rubric: (goalData?.rubric as string) ?? existing.rubric,
      started_at: (data.started_at as string) ?? existing.started_at,
    };
    if (event.run_id) next.runId = event.run_id;
    else if (existing.runId) next.runId = existing.runId;
    if (goalData?.max_iterations != null)
      next.max_iterations = goalData.max_iterations as number;
    else if (existing.max_iterations != null)
      next.max_iterations = existing.max_iterations;

    if (eventType === "goal:end") {
      next.ended_at = (data.ended_at as string) ?? undefined;
    }

    goal = next;
  }

  // Don't restore completed goals — only show the bar for still-active ones.
  if (!goal || !goal.objective || goal.ended_at) return null;
  return goal;
}

export function extractGoalsByRunFromEvents(
  events: HistoryEvent[],
): Record<string, ActiveGoalSpec> {
  const goalsByRunId: Record<string, ActiveGoalSpec> = {};

  for (const event of events) {
    const eventType = event.event_type;
    if (eventType !== "goal:start" && eventType !== "goal:end") continue;
    if (!event.run_id) continue;

    const data = event.data as Record<string, unknown> | null | undefined;
    if (!data) continue;

    const goalData = data.goal as Record<string, unknown> | undefined;
    const existing: ActiveGoalSpec = goalsByRunId[event.run_id] ?? {
      objective: "",
      runId: event.run_id,
    };

    const next: ActiveGoalSpec = {
      objective: (goalData?.objective as string) ?? existing.objective ?? "",
      rubric: (goalData?.rubric as string) ?? existing.rubric,
      runId: event.run_id,
      started_at: (data.started_at as string) ?? existing.started_at,
    };
    if (goalData?.max_iterations != null)
      next.max_iterations = goalData.max_iterations as number;
    else if (existing.max_iterations != null)
      next.max_iterations = existing.max_iterations;

    if (eventType === "goal:end") {
      next.ended_at = (data.ended_at as string) ?? existing.ended_at;
    } else if (existing.ended_at) {
      next.ended_at = existing.ended_at;
    }

    if (next.objective) {
      goalsByRunId[event.run_id] = next;
    }
  }

  return goalsByRunId;
}
