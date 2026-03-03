import type {
  Message,
  ToolCall,
  ToolResult,
  ToolPart,
  ThinkingPart,
  SandboxPart,
  FormField,
  MessageAttachment,
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
    msg = {
      id: crypto.randomUUID(),
      role: "assistant",
      content: "",
      timestamp: new Date(event.timestamp || Date.now()),
      parts: [],
      isStreaming: false,
    };
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
      const thinkingPart = createThinkingPart(
        eventData.content || "",
        thinkingId,
        depth,
        agentId,
        false,
      );
      const parts = msg.parts || [];
      if (depth > 0) {
        msg.parts = addPartToDepth(
          parts,
          thinkingPart,
          depth,
          opts.activeSubagentStack,
          agentId,
        );
      } else {
        const newParts = [...parts];
        let existingIndex = -1;

        // 如果有 thinking_id，精确匹配
        if (thinkingId !== undefined) {
          existingIndex = newParts.findIndex(
            (p) => p.type === "thinking" && p.thinking_id === thinkingId,
          );
        } else {
          // 如果没有 thinking_id，找最后一个 thinking part（且也没有 thinking_id）
          for (let i = newParts.length - 1; i >= 0; i--) {
            const p = newParts[i];
            if (p.type === "thinking" && p.thinking_id === undefined) {
              existingIndex = i;
              break;
            }
          }
        }

        if (existingIndex >= 0) {
          const existing = newParts[existingIndex] as ThinkingPart;
          newParts[existingIndex] = {
            ...existing,
            content: existing.content + (eventData.content || ""),
          };
        } else {
          newParts.push(thinkingPart);
        }
        msg.parts = newParts;
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
        const newParts = [...parts];
        const lastPart = newParts[newParts.length - 1];
        if (lastPart?.type === "text" && !lastPart.depth) {
          newParts[newParts.length - 1] = {
            ...lastPart,
            content: lastPart.content + content,
          };
        } else {
          newParts.push({ type: "text" as const, content });
        }
        msg.parts = newParts;
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
        let updated = false;
        const newParts = parts.map((p) => {
          if (
            p.type === "tool" &&
            p.name === toolName &&
            p.isPending &&
            !updated
          ) {
            updated = true;
            return {
              ...p,
              result: eventData.result || "",
              success: isSuccess,
              error: eventData.error,
              isPending: false,
            } as ToolPart;
          }
          return p;
        });
        msg.parts = newParts;
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
      const sandboxPart: SandboxPart = {
        type: "sandbox",
        status: "ready",
        sandbox_id: eventData.sandbox_id,
        work_dir: eventData.work_dir,
        timestamp: eventData.timestamp,
      };
      const parts = msg.parts || [];
      msg.parts = parts.map((p) =>
        p.type === "sandbox" && p.status === "starting" ? sandboxPart : p,
      );
      break;
    }

    case "sandbox:error": {
      const sandboxPart: SandboxPart = {
        type: "sandbox",
        status: "error",
        error: eventData.error,
        timestamp: eventData.timestamp,
      };
      const parts = msg.parts || [];
      msg.parts = parts.map((p) => (p.type === "sandbox" ? sandboxPart : p));
      break;
    }

    case "token:usage": {
      const tokenData = event.data as {
        input_tokens?: number;
        output_tokens?: number;
        total_tokens?: number;
        duration?: number;
      };
      msg.tokenUsage = {
        type: "token_usage",
        input_tokens: tokenData.input_tokens || 0,
        output_tokens: tokenData.output_tokens || 0,
        total_tokens: tokenData.total_tokens || 0,
      };
      msg.duration = tokenData.duration ? tokenData.duration * 1000 : undefined;
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
      });
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
 */
export function getLastEventTimestamp(events: HistoryEvent[]): Date | null {
  if (events.length === 0) return null;
  const sortedEvents = [...events].sort((a, b) => {
    const timeA = new Date(a.timestamp || 0).getTime();
    const timeB = new Date(b.timestamp || 0).getTime();
    return timeA - timeB;
  });
  const lastEvent = sortedEvents[sortedEvents.length - 1];
  return lastEvent?.timestamp ? new Date(lastEvent.timestamp) : null;
}
