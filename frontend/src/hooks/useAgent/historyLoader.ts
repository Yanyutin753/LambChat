/**
 * History event loader for useAgent hook
 * Reconstructs messages from stored events.
 *
 * Message transformation logic is unified in processMessageEvent (messageParts.ts).
 * This file handles: event iteration, message reconstruction, and
 * user:message / user:cancel / approval_required which are history-specific.
 */

import type { Message, MessagePart, FormField } from "../../types";
import { authFetch } from "../../services/api/fetch";
import i18n from "../../i18n";
import type {
  EventData,
  SubagentStackItem,
  HistoryEvent,
  HistoryEventData,
} from "./types";
import { convertAttachments, processMessageEvent } from "./eventProcessor";
import { clearAllLoadingStates } from "./messageParts";

interface ProcessHistoryOptions {
  options?: {
    onApprovalRequired?: (approval: {
      id: string;
      message: string;
      type: string;
      fields?: FormField[];
    }) => void;
  };
  activeSubagentStack: SubagentStackItem[];
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
  if (eventType === "metadata" || eventType === "done") {
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
      }>(`/human/${approvalData.id}`)
        .then((data) => data ?? null)
        .then((approval) => {
          if (approval?.status === "pending") {
            opts.options?.onApprovalRequired?.({
              id: approvalData.id!,
              message: approval.message || "",
              type: approval.type || "form",
              fields: approval.fields,
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
    const messageId = event.run_id || crypto.randomUUID();
    msg = {
      id: messageId,
      role: "assistant",
      content: "",
      timestamp: new Date(event.timestamp || Date.now()),
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
    const timeA = new Date(a.timestamp || 0).getTime();
    const timeB = new Date(b.timestamp || 0).getTime();
    return timeA - timeB;
  });

  const reconstructedMessages: Message[] = [];
  let currentAssistantMessage: Message | null = null;

  for (const event of sortedEvents) {
    const eventType = event.event_type;
    const eventData = event.data as HistoryEventData;

    // Handle user message separately
    if (eventType === "user:message") {
      if (currentAssistantMessage) {
        reconstructedMessages.push(currentAssistantMessage);
        currentAssistantMessage = null;
      }
      const userAttachments = convertAttachments(eventData.attachments);
      reconstructedMessages.push({
        id: crypto.randomUUID(),
        role: "user",
        content: eventData.content || "",
        timestamp: new Date(event.timestamp || Date.now()),
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
          id: crypto.randomUUID(),
          role: "assistant",
          content: "",
          timestamp: new Date(event.timestamp || Date.now()),
          parts: [{ type: "cancelled" }],
          runId: event.run_id,
        });
      }
      currentAssistantMessage = null;
      continue;
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

export function prepareMessagesForRunningRun(
  messages: Message[],
  runId: string,
  createId: () => string = () => crypto.randomUUID(),
): RunningAssistantPreparationResult {
  const existingAssistant = [...messages]
    .reverse()
    .find((message) => message.role === "assistant" && message.runId === runId);

  if (existingAssistant) {
    return {
      streamingMessageId: existingAssistant.id,
      messages: messages.map((message) =>
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
      ...messages,
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
  return lastEvent?.timestamp ? new Date(lastEvent.timestamp) : null;
}
