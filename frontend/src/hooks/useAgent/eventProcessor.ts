/**
 * Unified message event processor.
 *
 * Single source of truth for transforming message state in response to events.
 * Both streaming (eventHandlers.ts) and history (historyLoader.ts) delegate here.
 *
 * Side effects like subagent stack push/pop, connection status, etc.
 * are handled by the caller based on event type.
 */

import type {
  MessagePart,
  MessageAttachment,
  ToolCall,
  ToolResult,
  TokenUsagePart,
  SandboxPart,
  TodoPart,
  SummaryPart,
} from "../../types";
import i18n from "../../i18n";
import type { EventData, SubagentStackItem } from "./types";
import {
  addPartToDepth,
  createSubagentPart,
  createThinkingPart,
  createToolPart,
  updateSubagentResult,
  updateToolResultInDepth,
  clearAllLoadingStates,
} from "./messageParts";
import type { ThinkingPart } from "../../types";

// ============================================
// Shared utilities
// ============================================

/**
 * Convert backend attachment format to frontend format.
 */
export function convertAttachments(
  attachments?: Array<{
    id: string;
    key: string;
    name: string;
    type: string;
    mime_type: string;
    size: number;
    url: string;
  }>,
): MessageAttachment[] | undefined {
  return attachments?.map((a) => ({
    id: a.id,
    key: a.key,
    name: a.name,
    type: a.type as MessageAttachment["type"],
    mimeType: a.mime_type,
    size: a.size,
    url: a.url,
  }));
}

// ============================================
// Event processor
// ============================================

/**
 * Result of processing a message event.
 */
export interface ProcessMessageEventResult {
  parts: MessagePart[];
  content: string;
  toolCalls: ToolCall[];
  toolResult?: ToolResult;
  tokenUsage?: TokenUsagePart;
  duration?: number;
  cancelled?: boolean;
}

/**
 * Unified message event processor.
 */
export function processMessageEvent(
  eventType: string,
  data: EventData,
  parts: MessagePart[],
  content: string,
  toolCalls: ToolCall[],
  depth: number,
  subagentStack: SubagentStackItem[],
  isStreaming: boolean,
  messageId?: string,
): ProcessMessageEventResult {
  const result: ProcessMessageEventResult = { parts, content, toolCalls };
  const agentId = data.agent_id;

  switch (eventType) {
    // ---- Agent events ----

    case "agent:call": {
      const subagentPart = createSubagentPart(
        agentId || "unknown",
        data.agent_name || agentId || i18n.t("chat.unknownAgent"),
        data.input || "",
        depth,
        data.timestamp,
      );
      result.parts = addPartToDepth(
        parts,
        subagentPart,
        depth,
        subagentStack,
        agentId || "unknown",
        messageId,
      );
      break;
    }

    case "agent:result": {
      result.parts = updateSubagentResult(
        parts,
        agentId || "unknown",
        String(data.result || ""),
        data.success !== false,
        depth,
        data.error,
        data.timestamp,
      );
      break;
    }

    // ---- Thinking events ----

    case "thinking": {
      const thinkingContent = data.content || "";
      if (!thinkingContent) break;

      const thinkingPart = createThinkingPart(
        thinkingContent,
        data.thinking_id,
        depth,
        agentId,
        isStreaming,
      );

      if (depth > 0) {
        result.parts = addPartToDepth(
          parts,
          thinkingPart,
          depth,
          subagentStack,
          agentId,
          messageId,
        );
      } else {
        const newParts = [...parts];
        let existingIndex = -1;

        if (data.thinking_id !== undefined) {
          existingIndex = newParts.findIndex(
            (p) => p.type === "thinking" && p.thinking_id === data.thinking_id,
          );
        } else {
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
            content: existing.content + thinkingContent,
            isStreaming: isStreaming ? true : existing.isStreaming,
          };
        } else {
          newParts.push(thinkingPart);
        }
        result.parts = newParts;
      }
      break;
    }

    // ---- Message chunk events ----

    case "message:chunk": {
      const chunkContent = data.content || "";
      if (!chunkContent) break;

      if (depth > 0) {
        const textPart = {
          type: "text" as const,
          content: chunkContent,
          depth,
          agent_id: agentId,
        };
        result.parts = addPartToDepth(
          parts,
          textPart,
          depth,
          subagentStack,
          agentId,
          messageId,
        );
      } else {
        const newParts = [...parts];
        const lastPart = newParts[newParts.length - 1];
        if (lastPart?.type === "text" && !lastPart.depth) {
          newParts[newParts.length - 1] = {
            ...lastPart,
            content: lastPart.content + chunkContent,
          };
        } else {
          newParts.push({ type: "text" as const, content: chunkContent });
        }
        result.parts = newParts;
        result.content = content + chunkContent;
      }
      break;
    }

    // ---- Tool events ----

    case "tool:start": {
      const toolCallId = data.tool_call_id as string | undefined;
      const toolCall: ToolCall = {
        id: toolCallId,
        name: data.tool || "",
        args: data.args || {},
      };
      const toolPart = createToolPart(
        data.tool || "",
        data.args || {},
        depth,
        agentId,
        toolCallId,
      );

      if (depth > 0) {
        result.parts = addPartToDepth(
          parts,
          toolPart,
          depth,
          subagentStack,
          agentId,
          messageId,
        );
      } else {
        result.parts = [...parts, toolPart];
        result.toolCalls = [...toolCalls, toolCall];
      }
      break;
    }

    case "tool:result": {
      const toolCallId = data.tool_call_id as string | undefined;
      const toolName = data.tool || "";
      const isSuccess = data.success !== false;
      const errorMsg = data.error as string | undefined;
      const resultContent = data.result || "";

      if (depth > 0 || toolCallId) {
        result.parts = updateToolResultInDepth(
          parts,
          toolCallId || "",
          resultContent,
          isSuccess,
          errorMsg,
          depth,
          agentId,
        );
      } else {
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
              result: resultContent,
              success: isSuccess,
              error: errorMsg,
              isPending: false,
            };
          }
          return p;
        });
        result.parts = newParts;
        result.toolResult = {
          id: toolCallId,
          name: toolName,
          result: resultContent,
          success: isSuccess,
        };
      }
      break;
    }

    // ---- Sandbox events ----

    case "sandbox:starting": {
      const sandboxPart: SandboxPart = {
        type: "sandbox",
        status: "starting",
        timestamp: data.timestamp,
      };
      result.parts = upsertSandboxPart(parts, sandboxPart);
      break;
    }

    case "sandbox:ready": {
      const readyPart: SandboxPart = {
        type: "sandbox",
        status: "ready",
        sandbox_id: data.sandbox_id,
        work_dir: data.work_dir,
        timestamp: data.timestamp,
      };
      result.parts = upsertSandboxPart(parts, readyPart);
      break;
    }

    case "sandbox:error": {
      const errorPart: SandboxPart = {
        type: "sandbox",
        status: "error",
        error: data.error,
        timestamp: data.timestamp,
      };
      result.parts = upsertSandboxPart(parts, errorPart);
      break;
    }

    // ---- Token usage ----

    case "token:usage": {
      result.tokenUsage = {
        type: "token_usage",
        input_tokens: data.input_tokens || 0,
        output_tokens: data.output_tokens || 0,
        total_tokens: data.total_tokens || 0,
        cache_creation_tokens: data.cache_creation_tokens || 0,
        cache_read_tokens: data.cache_read_tokens || 0,
        model_id: data.model_id,
        model: data.model,
      };
      if (data.duration) result.duration = data.duration * 1000;
      break;
    }

    // ---- Error ----

    // ---- Todo events ----

    case "todo:updated": {
      const todos = (data.todos || []) as TodoPart["items"];
      if (!todos.length) break;
      const todoPart: TodoPart = { type: "todo", items: todos, isStreaming };
      if (depth > 0) {
        result.parts = addPartToDepth(
          parts,
          todoPart,
          depth,
          subagentStack,
          agentId,
          messageId,
        );
      } else {
        result.parts = upsertTodoPart(parts, todoPart);
      }
      break;
    }

    // ---- Summary events ----

    case "summary": {
      const summaryContent = data.content || "";
      if (!summaryContent) break;

      const summaryPart: SummaryPart = {
        type: "summary",
        content: summaryContent,
        summary_id: data.summary_id,
        depth,
        agent_id: agentId,
        isStreaming,
      };

      if (depth > 0) {
        result.parts = addPartToDepth(
          parts,
          summaryPart,
          depth,
          subagentStack,
          agentId,
          messageId,
        );
      } else {
        const newParts = [...parts];
        let lastSummaryIdx = -1;
        for (let i = newParts.length - 1; i >= 0; i--) {
          const p = newParts[i];
          if (p.type === "summary" && p.summary_id === data.summary_id) {
            lastSummaryIdx = i;
            break;
          }
        }
        if (lastSummaryIdx >= 0) {
          const existing = newParts[lastSummaryIdx] as SummaryPart;
          newParts[lastSummaryIdx] = {
            ...existing,
            content: existing.content + summaryContent,
          };
        } else {
          newParts.push(summaryPart);
        }
        result.parts = newParts;
      }
      break;
    }

    // ---- Error ----

    case "error": {
      const errorMsg = data.error || i18n.t("chat.unknownError");
      const isCancelled = data.type === "CancelledError";
      result.parts = isStreaming ? clearAllLoadingStates(parts) : parts;
      result.cancelled = isCancelled;
      if (!isCancelled) {
        result.content = i18n.t("chat.errorPrefix", { error: errorMsg });
      }
      break;
    }
  }

  return result;
}

// ============================================
// Internal helpers
// ============================================

/** Replace existing sandbox part or append if none exists. */
function upsertSandboxPart(
  parts: MessagePart[],
  sandboxPart: SandboxPart,
): MessagePart[] {
  return parts.some((p) => p.type === "sandbox")
    ? parts.map((p) => (p.type === "sandbox" ? sandboxPart : p))
    : [...parts, sandboxPart];
}

/** Replace existing todo part or append if none exists. */
function upsertTodoPart(
  parts: MessagePart[],
  todoPart: TodoPart,
): MessagePart[] {
  return parts.some((p) => p.type === "todo")
    ? parts.map((p) => (p.type === "todo" ? todoPart : p))
    : [...parts, todoPart];
}
