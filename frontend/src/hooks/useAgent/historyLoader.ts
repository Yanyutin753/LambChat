import type {
  Message,
  ToolCall,
  ToolResult,
  ToolPart,
  ThinkingPart,
  SandboxPart,
  FormField,
  MessageAttachment,
  MessagePart,
} from "../../types";
import type {
  SubagentStackItem,
  HistoryEvent,
  HistoryEventData,
} from "./types";
import {
  addPartToDepth,
  updateSubagentResult,
  updateToolResultInDepth,
  createSubagentPart,
  createThinkingPart,
  createToolPart,
} from "./messageParts";

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
 * Convert backend attachment format to frontend format.
 */
export function convertAttachments(
  attachments:
    | Array<{
        id: string;
        key: string;
        name: string;
        type: string;
        mime_type: string;
        size: number;
        url: string;
      }>
    | undefined,
): MessageAttachment[] | undefined {
  return attachments?.map((a) => ({
    id: a.id,
    key: a.key,
    name: a.name,
    type: a.type as "image" | "video" | "audio" | "document",
    mimeType: a.mime_type,
    size: a.size,
    url: a.url,
  }));
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

  // Skip user:cancel - handled separately in reconstructMessagesFromEvents
  // to preserve the current assistant message with cancelled state

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
      // Check approval status (async, fire and forget)
      fetch(`/human/${approvalData.id}`)
        .then((response) => (response.ok ? response.json() : null))
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

  // Ensure assistant message exists for other event types
  let msg = currentAssistantMessage;
  if (!msg) {
    // Use run_id as message ID for persistence across page refreshes
    // This ensures the same message gets the same ID, allowing ratings to be matched
    const messageId = event.run_id || crypto.randomUUID();
    msg = {
      id: messageId,
      role: "assistant",
      content: "",
      timestamp: new Date(event.timestamp || Date.now()),
      parts: [],
      isStreaming: false,
      // Extract run_id from event for message rating
      runId: event.run_id,
    };
  } else if (event.run_id && !msg.runId) {
    // Update existing message with run_id if not already set
    msg = { ...msg, runId: event.run_id };
  }

  switch (eventType) {
    case "agent:call": {
      const subagentPart = createSubagentPart(
        agentId || "unknown",
        eventData.agent_name || agentId || "Unknown Agent",
        eventData.input || "",
        depth,
      );
      const parts = msg.parts || [];
      msg.parts = addPartToDepth(
        parts,
        subagentPart,
        depth,
        opts.activeSubagentStack,
        agentId || "unknown",
      );
      break;
    }

    case "agent:result": {
      const parts = msg.parts || [];
      msg.parts = updateSubagentResult(
        parts,
        agentId || "unknown",
        eventData.result || "",
        eventData.success !== false,
        depth,
      );
      break;
    }

    case "thinking": {
      const thinkingId = eventData.thinking_id;
      const thinkingContent = eventData.content || "";
      const parts = msg.parts || [];
      if (depth > 0) {
        const thinkingPart = createThinkingPart(
          thinkingContent,
          thinkingId,
          depth,
          agentId,
          false,
        );
        msg.parts = addPartToDepth(
          parts,
          thinkingPart,
          depth,
          opts.activeSubagentStack,
          agentId,
        );
      } else {
        let existingIndex = -1;

        // 如果有 thinking_id，精确匹配
        if (thinkingId !== undefined) {
          for (let i = parts.length - 1; i >= 0; i--) {
            const p = parts[i];
            if (p.type === "thinking" && p.thinking_id === thinkingId) {
              existingIndex = i;
              break;
            }
          }
        } else {
          // 如果没有 thinking_id，找最后一个 thinking part（且也没有 thinking_id）
          for (let i = parts.length - 1; i >= 0; i--) {
            const p = parts[i];
            if (p.type === "thinking" && p.thinking_id === undefined) {
              existingIndex = i;
              break;
            }
          }
        }

        if (existingIndex >= 0) {
          // Mutate directly for better performance
          const existing = parts[existingIndex] as ThinkingPart;
          existing.content += thinkingContent;
          msg.parts = parts;
        } else {
          const thinkingPart = createThinkingPart(
            thinkingContent,
            thinkingId,
            depth,
            agentId,
            false,
          );
          msg.parts = [...parts, thinkingPart];
        }
      }
      break;
    }

    case "message:chunk": {
      const content = eventData.content || "";
      if (depth > 0) {
        const textPart = {
          type: "text" as const,
          content,
          depth,
          agent_id: agentId,
        };
        const parts = msg.parts || [];
        msg.parts = addPartToDepth(
          parts,
          textPart,
          depth,
          opts.activeSubagentStack,
          agentId,
        );
      } else {
        msg.content += content;
        const parts = msg.parts || [];
        const lastPart = parts[parts.length - 1];
        if (lastPart?.type === "text" && !lastPart.depth) {
          // Mutate directly for better performance
          (lastPart as { content: string }).content += content;
          msg.parts = parts;
        } else {
          msg.parts = [...parts, { type: "text" as const, content }];
        }
      }
      break;
    }

    case "tool:start": {
      const toolCallId = eventData.tool_call_id;
      const toolCall: ToolCall = {
        id: toolCallId,
        name: eventData.tool || "",
        args: eventData.args || {},
      };
      const toolPart = createToolPart(
        eventData.tool || "",
        eventData.args || {},
        depth,
        agentId,
        toolCallId,
      );
      const parts = msg.parts || [];
      if (depth > 0) {
        msg.parts = addPartToDepth(
          parts,
          toolPart,
          depth,
          opts.activeSubagentStack,
          agentId,
        );
      } else {
        msg.parts = [...parts, toolPart];
        msg.toolCalls = [...(msg.toolCalls || []), toolCall];
      }
      break;
    }

    case "tool:result": {
      const toolCallId = eventData.tool_call_id;
      const isSuccess =
        eventData.success !== false &&
        !eventData.result?.toString().startsWith("Error:");
      const toolResult: ToolResult = {
        id: toolCallId,
        name: eventData.tool || "",
        result: eventData.result || "",
        success: isSuccess,
      };
      const parts = msg.parts || [];
      if (depth > 0 || toolCallId) {
        msg.parts = updateToolResultInDepth(
          parts,
          toolCallId || "",
          eventData.result || "",
          isSuccess,
          eventData.error,
          depth,
          agentId,
        );
      } else {
        // 向后兼容：按 name 匹配
        const toolName = eventData.tool || "";
        const resultContent = eventData.result || "";
        let updated = false;
        for (let i = 0; i < parts.length; i++) {
          const p = parts[i];
          if (
            p.type === "tool" &&
            p.name === toolName &&
            (p as ToolPart).isPending &&
            !updated
          ) {
            updated = true;
            // Mutate directly for better performance
            const toolPart = p as ToolPart;
            toolPart.result = resultContent;
            toolPart.success = isSuccess;
            toolPart.error = eventData.error;
            toolPart.isPending = false;
            break;
          }
        }
        msg.parts = parts;
        msg.toolResults = [...(msg.toolResults || []), toolResult];
      }
      break;
    }

    case "sandbox:starting": {
      const sandboxPart: SandboxPart = {
        type: "sandbox",
        status: "starting",
        timestamp: eventData.timestamp,
      };
      const parts = msg.parts || [];
      msg.parts = [...parts, sandboxPart];
      break;
    }

    case "sandbox:ready": {
      const parts = msg.parts || [];
      // Find and update existing sandbox in place
      for (let i = 0; i < parts.length; i++) {
        const p = parts[i];
        if (p.type === "sandbox" && p.status === "starting") {
          (p as SandboxPart).status = "ready";
          (p as SandboxPart).sandbox_id = eventData.sandbox_id;
          (p as SandboxPart).work_dir = eventData.work_dir;
          (p as SandboxPart).timestamp = eventData.timestamp;
          break;
        }
      }
      msg.parts = parts;
      break;
    }

    case "sandbox:error": {
      const parts = msg.parts || [];
      // Update all sandbox parts to error state
      for (let i = 0; i < parts.length; i++) {
        const p = parts[i];
        if (p.type === "sandbox") {
          (p as SandboxPart).status = "error";
          (p as SandboxPart).error = eventData.error;
          (p as SandboxPart).timestamp = eventData.timestamp;
        }
      }
      msg.parts = parts;
      break;
    }

    case "token:usage": {
      const tokenData = event.data as {
        input_tokens?: number;
        output_tokens?: number;
        total_tokens?: number;
        duration?: number;
        cache_creation_tokens?: number;
        cache_read_tokens?: number;
      };
      msg.tokenUsage = {
        type: "token_usage",
        input_tokens: tokenData.input_tokens || 0,
        output_tokens: tokenData.output_tokens || 0,
        total_tokens: tokenData.total_tokens || 0,
        cache_creation_tokens: tokenData.cache_creation_tokens || 0,
        cache_read_tokens: tokenData.cache_read_tokens || 0,
      };
      msg.duration = tokenData.duration ? tokenData.duration * 1000 : undefined;
      break;
    }

    case "error": {
      const errorData = event.data as {
        error?: string;
        type?: string;
      };
      if (errorData.type === "CancelledError") {
        // If currentAssistantMessage is null (already handled by user:cancel),
        // don't create a new message to avoid duplicates
        if (!currentAssistantMessage) {
          return null;
        }
        msg.cancelled = true;
      } else {
        msg.content = `Error: ${errorData.error || "Unknown error"}`;
      }
      break;
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
        // Include run_id for message rating
        runId: event.run_id,
      });
      continue;
    }

    // Handle user cancel - add cancelled part to current assistant message
    // Also mark all pending/running states as completed
    if (eventType === "user:cancel") {
      if (currentAssistantMessage) {
        // Mark all pending tools as completed and stop streaming states
        const updatedParts = (currentAssistantMessage.parts || []).map(
          (part): MessagePart => {
            // Tool: mark as not pending
            if (part.type === "tool" && part.isPending) {
              return {
                ...part,
                isPending: false,
                result: part.result || "Cancelled",
                success: false,
              };
            }
            // Thinking: stop streaming
            if (part.type === "thinking" && part.isStreaming) {
              return {
                ...part,
                isStreaming: false,
              };
            }
            return part;
          },
        );
        // Also stop streaming on the main message
        const updatedMessage = {
          ...currentAssistantMessage,
          isStreaming: false,
          parts: [...updatedParts, { type: "cancelled" as const }],
        };
        reconstructedMessages.push(updatedMessage);
      } else {
        // Create an empty assistant message with cancelled part
        reconstructedMessages.push({
          id: crypto.randomUUID(),
          role: "assistant",
          content: "",
          timestamp: new Date(event.timestamp || Date.now()),
          parts: [{ type: "cancelled" }],
          // Include run_id for feedback/rating
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

/**
 * Get the last event timestamp from sorted events.
 * Uses the already sorted array to avoid re-sorting.
 */
export function getLastEventTimestamp(events: HistoryEvent[]): Date | null {
  if (events.length === 0) return null;
  // Find last event with timestamp (events should already be sorted by caller)
  let lastEvent: HistoryEvent | null = null;
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].timestamp) {
      lastEvent = events[i];
      break;
    }
  }
  return lastEvent?.timestamp ? new Date(lastEvent.timestamp) : null;
}
