/**
 * Stream event handlers for useAgent hook
 * Handles all incoming SSE events and updates messages accordingly
 */

import type {
  Message,
  ToolCall,
  ToolResult,
  ThinkingPart,
  MessagePart,
  SandboxPart,
  TokenUsagePart,
  MessageAttachment,
} from "../../types";
import type {
  StreamEvent,
  EventData,
  SubagentStackItem,
  UseAgentOptions,
} from "./types";
import {
  addPartToDepth,
  updateSubagentResult,
  updateToolResultInDepth,
  createToolPart,
  createThinkingPart,
  createSubagentPart,
} from "./messageParts";

/**
 * Convert backend attachments to frontend format
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
  if (!attachments) return undefined;
  return attachments.map((a) => ({
    id: a.id,
    key: a.key,
    name: a.name,
    type: a.type as MessageAttachment["type"],
    mimeType: a.mime_type,
    size: a.size,
    url: a.url,
  }));
}

/**
 * Context passed to event handler
 */
export interface EventHandlerContext {
  options?: UseAgentOptions;
  sessionIdRef: React.MutableRefObject<string | null>;
  processedEventIdsRef: React.MutableRefObject<Set<string>>;
  lastHistoryTimestampRef: React.MutableRefObject<Date | null>;
  activeSubagentStackRef: React.MutableRefObject<SubagentStackItem[]>;
  setSessionId: (id: string) => void;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  setConnectionStatus: (status: string) => void;
  setIsInitializingSandbox: (loading: boolean) => void;
  setSandboxError: (error: string | null) => void;
}

/**
 * Handle incoming SSE events
 */
export function handleStreamEvent(
  event: StreamEvent,
  messageId: string,
  eventId: string,
  eventTimestamp: string | undefined,
  ctx: EventHandlerContext,
): void {
  console.log("[handleStreamEvent] Received event:", {
    eventType: event.event,
    messageId,
    eventId,
  });

  // Skip if already processed by ID
  if (ctx.processedEventIdsRef.current.has(eventId)) {
    console.log("[SSE] Skipping duplicate event by ID:", eventId);
    return;
  }

  // Skip if this event is older than the last history timestamp
  if (eventTimestamp && ctx.lastHistoryTimestampRef.current) {
    const eventTime = new Date(eventTimestamp);
    const historyTime = ctx.lastHistoryTimestampRef.current;
    if (eventTime < historyTime) {
      console.log(
        "[SSE] Skipping duplicate event by timestamp:",
        eventId,
        eventTime.toISOString(),
        "<",
        historyTime.toISOString(),
      );
      return;
    }
  }

  ctx.processedEventIdsRef.current.add(eventId);

  const eventType = event.event;
  let data: EventData = {};
  try {
    data = JSON.parse(event.data);
  } catch {
    // Fallback for non-JSON data
  }

  const depth = data.depth || 0;

  switch (eventType) {
    case "metadata": {
      if (data.session_id && !ctx.sessionIdRef.current) {
        ctx.setSessionId(data.session_id);
      }
      break;
    }

    case "user:message": {
      handleUserMessage(data, messageId, eventTimestamp, ctx);
      break;
    }

    case "agent:call": {
      handleAgentCall(data, messageId, depth, ctx);
      break;
    }

    case "agent:result": {
      handleAgentResult(data, messageId, depth, ctx);
      break;
    }

    case "thinking": {
      handleThinking(data, messageId, depth, ctx);
      break;
    }

    case "message:chunk": {
      handleMessageChunk(data, messageId, depth, ctx);
      break;
    }

    case "tool:start": {
      handleToolStart(data, messageId, depth, ctx);
      break;
    }

    case "tool:result": {
      handleToolResult(data, messageId, depth, ctx);
      break;
    }

    case "done": {
      ctx.setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId ? { ...m, isStreaming: false } : m,
        ),
      );
      ctx.setConnectionStatus("disconnected");
      break;
    }

    case "error": {
      handleError(data, messageId, ctx);
      break;
    }

    case "approval_required": {
      handleApprovalRequired(data, ctx);
      break;
    }

    case "sandbox:starting": {
      handleSandboxStarting(data, messageId, ctx);
      break;
    }

    case "sandbox:state": {
      handleSandboxState(data, messageId, ctx);
      break;
    }

    case "sandbox:ready": {
      handleSandboxReady(data, messageId, ctx);
      break;
    }

    case "sandbox:error": {
      handleSandboxError(data, messageId, ctx);
      break;
    }

    case "token:usage": {
      handleTokenUsage(data, messageId, ctx);
      break;
    }
  }
}

// Individual event handlers

function handleUserMessage(
  data: EventData,
  _messageId: string,
  eventTimestamp: string | undefined,
  ctx: EventHandlerContext,
): void {
  const userContent = data.content || "";
  const userAttachments = convertAttachments(data.attachments);

  if (userContent) {
    ctx.setMessages((prev) => {
      if (prev.length === 0) {
        const newUserMessage: Message = {
          id: crypto.randomUUID(),
          role: "user",
          content: userContent,
          timestamp: eventTimestamp ? new Date(eventTimestamp) : new Date(),
          attachments: userAttachments,
        };
        return [...prev, newUserMessage];
      }
      const existingUserMsg = prev.find(
        (m) => m.role === "user" && m.content === userContent,
      );
      if (existingUserMsg) return prev;

      const newUserMessage: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content: userContent,
        timestamp: eventTimestamp ? new Date(eventTimestamp) : new Date(),
        attachments: userAttachments,
      };
      const streamingAssistantIndex = prev.findIndex(
        (m) => m.role === "assistant" && m.isStreaming,
      );
      if (streamingAssistantIndex !== -1) {
        const newMessages = [...prev];
        newMessages.splice(streamingAssistantIndex, 0, newUserMessage);
        return newMessages;
      }
      return [...prev, newUserMessage];
    });
  }
}

function handleAgentCall(
  data: EventData,
  messageId: string,
  depth: number,
  ctx: EventHandlerContext,
): void {
  const agentId = data.agent_id || "unknown";
  const subagentPart = createSubagentPart(
    agentId,
    data.agent_name || data.agent_id || "Unknown Agent",
    data.input || "",
    depth,
  );

  ctx.activeSubagentStackRef.current.push({
    agent_id: agentId,
    depth: depth,
    message_id: messageId,
  });

  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      const parts = m.parts || [];
      const newParts = addPartToDepth(
        parts,
        subagentPart,
        depth,
        ctx.activeSubagentStackRef.current,
        agentId,
        messageId,
      );
      return { ...m, parts: newParts };
    }),
  );
}

function handleAgentResult(
  data: EventData,
  messageId: string,
  depth: number,
  ctx: EventHandlerContext,
): void {
  const agentId = data.agent_id || "unknown";
  const stackIndex = ctx.activeSubagentStackRef.current.findIndex(
    (item) => item.agent_id === agentId && item.message_id === messageId,
  );
  if (stackIndex !== -1) {
    ctx.activeSubagentStackRef.current.splice(stackIndex, 1);
  }

  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      const parts = m.parts || [];
      const newParts = updateSubagentResult(
        parts,
        agentId,
        data.result || "",
        data.success !== false,
        depth,
      );
      return { ...m, parts: newParts };
    }),
  );
}

function handleThinking(
  data: EventData,
  messageId: string,
  depth: number,
  ctx: EventHandlerContext,
): void {
  const content = data.content || "";
  const thinkingId = data.thinking_id;
  if (content) {
    const thinkingPart = createThinkingPart(
      content,
      thinkingId,
      depth,
      data.agent_id,
      true,
    );
    ctx.setMessages((prev) =>
      prev.map((m) => {
        if (m.id !== messageId) return m;
        const parts = m.parts || [];
        if (depth > 0) {
          const newParts = addPartToDepth(
            parts,
            thinkingPart,
            depth,
            ctx.activeSubagentStackRef.current,
            data.agent_id as string,
            messageId,
          );
          return { ...m, parts: newParts };
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
              content: existing.content + content,
              isStreaming: true,
            };
          } else {
            newParts.push(thinkingPart);
          }
          return { ...m, parts: newParts };
        }
      }),
    );
  }
}

function handleMessageChunk(
  data: EventData,
  messageId: string,
  depth: number,
  ctx: EventHandlerContext,
): void {
  const content = data.content || "";
  if (content) {
    ctx.setMessages((prev) => {
      const targetMessage = prev.find((m) => m.id === messageId);
      if (!targetMessage) return prev;

      return prev.map((m) => {
        if (m.id !== messageId) return m;
        const parts = m.parts || [];

        if (depth > 0) {
          const textPart = {
            type: "text" as const,
            content,
            depth,
            agent_id: data.agent_id,
          };
          const newParts = addPartToDepth(
            parts,
            textPart,
            depth,
            ctx.activeSubagentStackRef.current,
            data.agent_id as string,
            messageId,
          );
          return { ...m, parts: newParts };
        } else {
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
          return {
            ...m,
            content: m.content + content,
            parts: newParts,
          };
        }
      });
    });
  }
}

function handleToolStart(
  data: EventData,
  messageId: string,
  depth: number,
  ctx: EventHandlerContext,
): void {
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
    data.agent_id as string | undefined,
    toolCallId,
  );
  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      const parts = m.parts || [];
      let newParts: MessagePart[];

      if (depth > 0) {
        newParts = addPartToDepth(
          parts,
          toolPart,
          depth,
          ctx.activeSubagentStackRef.current,
          data.agent_id as string,
          messageId,
        );
      } else {
        newParts = [...parts, toolPart];
      }
      return {
        ...m,
        toolCalls:
          depth === 0 ? [...(m.toolCalls || []), toolCall] : m.toolCalls,
        parts: newParts,
      };
    }),
  );
}

function handleToolResult(
  data: EventData,
  messageId: string,
  depth: number,
  ctx: EventHandlerContext,
): void {
  const toolCallId = data.tool_call_id as string | undefined;
  const toolName = data.tool || "";
  const isSuccess =
    data.success !== false && !data.result?.toString().startsWith("Error:");
  const toolResult: ToolResult = {
    id: toolCallId,
    name: toolName,
    result: data.result || "",
    success: isSuccess,
  };
  const errorMsg = data.error as string | undefined;

  // 只针对 add_skill_from_path 工具处理 callback
  if (toolName === "add_skill_from_path" && isSuccess && data.result) {
    try {
      let jsonStr = data.result;

      // 提取 content='...' 中的 JSON
      const contentMatch = jsonStr.match(/content='((?:[^'\\]|\\.)*)'/);
      if (contentMatch) {
        jsonStr = contentMatch[1].replace(/\\'/g, "'");
      }

      const resultObj = JSON.parse(jsonStr) as Record<string, unknown>;

      if (resultObj.callback) {
        const callback = resultObj.callback as Record<string, unknown>;
        console.log(`[SSE] Callback triggered: ${callback.type}`, callback);

        if (callback.type === "skill_added" && ctx.options?.onSkillAdded) {
          ctx.options.onSkillAdded(
            (callback.name as string) || "",
            (callback.description as string) || "",
            (callback.files_count as number) || 0,
          );
        }
      }
    } catch (e) {
      console.warn("[SSE] Failed to parse add_skill_from_path result:", e);
    }
  }

  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      const parts = m.parts || [];

      if (depth > 0 || toolCallId) {
        // 优先使用 tool_call_id 匹配
        const newParts = updateToolResultInDepth(
          parts,
          toolCallId || "",
          toolResult.result,
          toolResult.success,
          errorMsg,
          depth,
          data.agent_id as string,
        );
        return { ...m, parts: newParts };
      } else {
        // 向后兼容：按 name 匹配
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
              result: toolResult.result,
              success: toolResult.success,
              error: errorMsg,
              isPending: false,
            };
          }
          return p;
        });
        return {
          ...m,
          toolResults: [...(m.toolResults || []), toolResult],
          parts: newParts,
        };
      }
    }),
  );
}

function handleError(
  data: EventData,
  messageId: string,
  ctx: EventHandlerContext,
): void {
  const errorMsg = data.error || "Unknown error";
  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      return {
        ...m,
        content: `Error: ${errorMsg}`,
        isStreaming: false,
      };
    }),
  );
  ctx.setConnectionStatus("disconnected");
  ctx.options?.onClearApprovals?.();
}

async function handleApprovalRequired(
  data: EventData,
  ctx: EventHandlerContext,
): Promise<void> {
  if (data.id && ctx.options?.onApprovalRequired) {
    try {
      const response = await fetch(`/human/${data.id}`);
      if (!response.ok) return;
      const approval = await response.json();
      if (approval && approval.status === "pending") {
        ctx.options?.onApprovalRequired?.({
          id: data.id!,
          message: approval.message || "",
          type: approval.type || "form",
          fields: approval.fields || [],
        });
      }
    } catch (err) {
      console.warn("[SSE] Failed to check approval status:", err);
    }
  }
}

function handleSandboxStarting(
  data: EventData,
  messageId: string,
  ctx: EventHandlerContext,
): void {
  ctx.setIsInitializingSandbox(true);
  ctx.setSandboxError(null);
  const startingPart: SandboxPart = {
    type: "sandbox",
    status: "starting",
    timestamp: data.timestamp,
  };
  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      const parts = m.parts || [];
      const newParts = parts.some((p) => p.type === "sandbox")
        ? parts.map((p) => (p.type === "sandbox" ? startingPart : p))
        : [...parts, startingPart];
      return { ...m, parts: newParts };
    }),
  );
}

function handleSandboxState(
  data: EventData,
  messageId: string,
  ctx: EventHandlerContext,
): void {
  const statePart: SandboxPart = {
    type: "sandbox",
    status: data.state as "starting" | "ready" | "error",
    timestamp: data.timestamp,
  };
  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      const parts = m.parts || [];
      const newParts = parts.some((p) => p.type === "sandbox")
        ? parts.map((p) => (p.type === "sandbox" ? statePart : p))
        : [...parts, statePart];
      return { ...m, parts: newParts };
    }),
  );
}

function handleSandboxReady(
  data: EventData,
  messageId: string,
  ctx: EventHandlerContext,
): void {
  ctx.setIsInitializingSandbox(false);
  const readyPart: SandboxPart = {
    type: "sandbox",
    status: "ready",
    sandbox_id: data.sandbox_id,
    work_dir: data.work_dir,
    timestamp: data.timestamp,
  };
  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      const parts = m.parts || [];
      const newParts = parts.some((p) => p.type === "sandbox")
        ? parts.map((p) => (p.type === "sandbox" ? readyPart : p))
        : [...parts, readyPart];
      return { ...m, parts: newParts };
    }),
  );
}

function handleSandboxError(
  data: EventData,
  messageId: string,
  ctx: EventHandlerContext,
): void {
  ctx.setIsInitializingSandbox(false);
  ctx.setSandboxError(data.error || "沙箱初始化失败");
  const errorPart: SandboxPart = {
    type: "sandbox",
    status: "error",
    error: data.error,
    timestamp: data.timestamp,
  };
  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      const parts = m.parts || [];
      const newParts = parts.some((p) => p.type === "sandbox")
        ? parts.map((p) => (p.type === "sandbox" ? errorPart : p))
        : [...parts, errorPart];
      return { ...m, parts: newParts };
    }),
  );
}

function handleTokenUsage(
  data: EventData,
  messageId: string,
  ctx: EventHandlerContext,
): void {
  const tokenUsage: TokenUsagePart = {
    type: "token_usage",
    input_tokens: data.input_tokens || 0,
    output_tokens: data.output_tokens || 0,
    total_tokens: data.total_tokens || 0,
    cache_creation_tokens: data.cache_creation_tokens || 0,
    cache_read_tokens: data.cache_read_tokens || 0,
  };
  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      return {
        ...m,
        tokenUsage,
        duration: data.duration ? data.duration * 1000 : undefined,
      };
    }),
  );
}
