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
  RecommendQuestion,
  ArtifactPartArtifact,
  WorkflowPart,
} from "../../types";
import i18n from "../../i18n";
import { translateBackendError } from "../../utils/backendErrors";
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
        data.agent_avatar,
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

    // ---- Workflow events ----

    case "workflow:run": {
      const workflowPart: WorkflowPart = {
        type: "workflow",
        plugin_id: data.plugin_id,
        workflow_id: data.workflow_id,
        run_id: data.run_id,
        version_id: data.version_id,
        status: data.status,
        output: data.output,
        error: data.error,
        interface: data.interface,
        next_action: data.next_action,
        io_contract: data.io_contract,
        output_contract: data.output_contract,
        depth,
        agent_id: agentId,
        timestamp: data.timestamp,
      };

      if (depth > 0) {
        result.parts = addPartToDepth(
          parts,
          workflowPart,
          depth,
          subagentStack,
          agentId,
          messageId,
        );
      } else {
        result.parts = [...parts, workflowPart];
      }
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

        // Reverse scan: matching thinking part is usually at the end
        for (let i = newParts.length - 1; i >= 0; i--) {
          const p = newParts[i];
          if (p.type === "thinking") {
            const tid = (p as ThinkingPart).thinking_id;
            if (
              data.thinking_id !== undefined
                ? tid === data.thinking_id
                : tid === undefined
            ) {
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
        data.timestamp as string | undefined,
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
      const completedAt = data.timestamp as string | undefined;

      if (depth > 0 || toolCallId) {
        result.parts = updateToolResultInDepth(
          parts,
          toolCallId || "",
          resultContent,
          isSuccess,
          errorMsg,
          depth,
          agentId,
          completedAt,
        );
        if (depth === 0) {
          result.toolResult = {
            id: toolCallId,
            name: toolName,
            result: resultContent,
            success: isSuccess,
          };
        }
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
              completedAt,
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

    // ---- Artifact events ----

    case "artifact:result": {
      const artifact = data.artifact as ArtifactPartArtifact | undefined;
      if (!artifact) break;

      const artifactPart = {
        type: "artifact" as const,
        artifact,
        success: data.success !== false,
        error: data.error as string | undefined,
        depth,
        agent_id: agentId,
        completedAt: data.timestamp as string | undefined,
      };

      if (depth > 0) {
        result.parts = addPartToDepth(
          parts,
          artifactPart,
          depth,
          subagentStack,
          agentId,
          messageId,
        );
      } else {
        result.parts = [...parts, artifactPart];
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
        completedAt: data.timestamp,
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
        completedAt: data.timestamp,
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

    // ---- Recommended follow-up questions ----

    case "recommend:questions":
    case "followup:questions": {
      const questions = normalizeRecommendQuestions(data.questions);
      if (!questions.length) break;

      const recommendPart = {
        type: "recommend_questions" as const,
        questions,
        depth,
        agent_id: agentId,
      };

      if (depth > 0) {
        result.parts = addPartToDepth(
          parts,
          recommendPart,
          depth,
          subagentStack,
          agentId,
          messageId,
        );
      } else {
        result.parts = upsertRecommendQuestionsPart(parts, recommendPart);
      }
      break;
    }

    // ---- Completion ----

    case "complete":
    case "done": {
      result.parts = clearAllLoadingStates(parts);
      break;
    }

    // ---- Error ----

    case "error": {
      const errorMsg = data.error
        ? translateBackendError(data.error, i18n.t.bind(i18n))
        : i18n.t("chat.unknownError");
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

/** Replace existing sandbox part or append if none exists.
 *  Preserves `startedAt` from the previous part so the original
 *  starting timestamp survives across status transitions. */
function upsertSandboxPart(
  parts: MessagePart[],
  sandboxPart: SandboxPart,
): MessagePart[] {
  return parts.some((p) => p.type === "sandbox")
    ? parts.map((p) => {
        if (p.type !== "sandbox") return p;
        const prevStartedAt = p.startedAt;
        return {
          ...sandboxPart,
          startedAt: sandboxPart.startedAt ?? prevStartedAt,
        };
      })
    : [
        ...parts,
        {
          ...sandboxPart,
          startedAt: sandboxPart.startedAt ?? sandboxPart.timestamp,
        },
      ];
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

function normalizeRecommendQuestions(
  questions: EventData["questions"],
): RecommendQuestion[] {
  if (!Array.isArray(questions)) return [];

  return questions
    .map((question) => {
      if (typeof question === "string") {
        const content = question.trim();
        return content ? { content } : null;
      }

      const content = (
        question.content ||
        question.text ||
        question.title ||
        ""
      ).trim();
      if (!content) return null;

      return {
        content,
        upload: question.upload || question.data_upload,
      };
    })
    .filter((question): question is RecommendQuestion => question !== null);
}

function upsertRecommendQuestionsPart(
  parts: MessagePart[],
  recommendPart: Extract<MessagePart, { type: "recommend_questions" }>,
): MessagePart[] {
  return parts.some((p) => p.type === "recommend_questions")
    ? parts.map((p) => (p.type === "recommend_questions" ? recommendPart : p))
    : [...parts, recommendPart];
}
