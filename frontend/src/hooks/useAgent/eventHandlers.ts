/**
 * Stream event handlers for useAgent hook
 * Handles all incoming SSE events and updates messages accordingly.
 *
 * Message transformation logic is unified in processMessageEvent (messageParts.ts).
 * This file handles: SSE parsing, duplicate detection, subagent stack management,
 * and React state updates (side effects).
 */

import type { Message, FormField } from "../../types";
import { authFetch } from "../../services/api/fetch";
import i18n from "../../i18n";
import type {
  StreamEvent,
  EventData,
  SubagentStackItem,
  UseAgentOptions,
} from "./types";
import { clearAllLoadingStates } from "./messageParts";
import { convertAttachments, processMessageEvent } from "./eventProcessor";

/**
 * Context passed to event handler
 */
export interface EventHandlerContext {
  options?: UseAgentOptions;
  sessionIdRef: React.MutableRefObject<string | null>;
  processedEventIdsRef: React.MutableRefObject<Set<string>>;
  lastHistoryTimestampRef: React.MutableRefObject<Date | null>;
  activeSubagentStackRef: React.MutableRefObject<SubagentStackItem[]>;
  streamVersionRef: React.MutableRefObject<number>;
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
    if (eventTime <= historyTime) {
      console.log(
        "[SSE] Skipping duplicate event by timestamp:",
        eventId,
        eventTime.toISOString(),
        "<=",
        historyTime.toISOString(),
      );
      return;
    }
  }

  ctx.processedEventIdsRef.current.add(eventId);

  // Cap the dedup set to prevent unbounded memory growth during long streams.
  // Safe to clear: event dedup is only needed within a single streaming session,
  // and the set is fully cleared on loadHistory/sendMessage/clearMessages.
  if (ctx.processedEventIdsRef.current.size > 10_000) {
    ctx.processedEventIdsRef.current.clear();
  }

  // Capture stream version at event processing time to detect stale events.
  // If clearMessages() was called while SSE events were still in-flight,
  // the version will have been incremented and these stale events should be dropped.
  const streamVersion = ctx.streamVersionRef.current;

  const eventType = event.event;
  let data: EventData = {};
  try {
    data = JSON.parse(event.data);
  } catch {
    // Fallback for non-JSON data
  }

  const depth = data.depth || 0;

  // Events handled entirely by side effects (no message transformation)
  switch (eventType) {
    case "metadata": {
      if (
        data.session_id &&
        !ctx.sessionIdRef.current &&
        ctx.streamVersionRef.current === streamVersion
      ) {
        ctx.setSessionId(data.session_id);
      }
      return;
    }

    case "user:message": {
      handleUserMessage(data, messageId, eventTimestamp, ctx);
      return;
    }

    case "user:cancel": {
      handleError(data, messageId, ctx, true);
      return;
    }

    case "done": {
      ctx.setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? {
                ...m,
                isStreaming: false,
                parts: clearAllLoadingStates(m.parts || []),
              }
            : m,
        ),
      );
      ctx.setConnectionStatus("disconnected");
      return;
    }

    case "queue_update": {
      if (data.status === "processing") {
        import("react-hot-toast").then(({ default: toast }) => {
          toast.dismiss("chat-queue");
          toast.success(i18n.t("chat.queueStart"), { duration: 2000 });
        });
      }
      return;
    }

    case "approval_required": {
      handleApprovalRequired(data, ctx);
      return;
    }

    case "skills:changed": {
      if (ctx.options?.onSkillAdded) {
        const action = (data.action as string) || "updated";
        const description =
          action === "created"
            ? i18n.t("chat.skillCreated")
            : i18n.t("chat.skillUpdated");
        ctx.options.onSkillAdded(
          (data.skill_name as string) || "",
          description,
          (data.files_count as number) || 0,
        );
      }
      return;
    }
  }

  // Drop stale events if clearMessages() was called mid-stream
  if (ctx.streamVersionRef.current !== streamVersion) {
    return;
  }

  // Only process known message-transforming event types
  const MESSAGE_EVENTS = new Set([
    "agent:call",
    "agent:result",
    "thinking",
    "message:chunk",
    "tool:start",
    "tool:result",
    "sandbox:starting",
    "sandbox:ready",
    "sandbox:error",
    "token:usage",
    "todo:updated",
    "summary",
    "error",
  ]);
  if (!MESSAGE_EVENTS.has(eventType)) {
    console.warn("[SSE] Unhandled event type:", eventType);
    return;
  }

  // Events that transform message state via processMessageEvent
  const subagentStack = ctx.activeSubagentStackRef.current;

  // Manage subagent stack as side effect
  if (eventType === "agent:call") {
    const agentId = data.agent_id || "unknown";
    subagentStack.push({ agent_id: agentId, depth, message_id: messageId });
  }

  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;

      const result = processMessageEvent(
        eventType,
        data,
        m.parts || [],
        m.content,
        m.toolCalls || [],
        depth,
        subagentStack,
        true, // isStreaming
        messageId,
      );

      const updated = {
        ...m,
        parts: result.parts,
        content: result.content,
        toolCalls: result.toolCalls,
      };

      if (result.toolResult) {
        updated.toolResults = [...(m.toolResults || []), result.toolResult];
      }
      if (result.tokenUsage) {
        updated.tokenUsage = result.tokenUsage;
      }
      if (result.duration) {
        updated.duration = result.duration;
      }
      if (result.cancelled) {
        updated.isStreaming = false;
        updated.cancelled = true;
      }

      return updated;
    }),
  );

  // Pop subagent stack after agent:result
  if (eventType === "agent:result") {
    const agentId = data.agent_id || "unknown";
    const stackIndex = subagentStack.findIndex(
      (item) => item.agent_id === agentId && item.message_id === messageId,
    );
    if (stackIndex !== -1) {
      subagentStack.splice(stackIndex, 1);
    }
  }

  // Sandbox side effects
  if (eventType === "sandbox:starting") {
    ctx.setIsInitializingSandbox(true);
    ctx.setSandboxError(null);
  }
  if (eventType === "sandbox:ready") {
    ctx.setIsInitializingSandbox(false);
  }
  if (eventType === "sandbox:error") {
    ctx.setIsInitializingSandbox(false);
    ctx.setSandboxError(data.error || i18n.t("chat.sandboxInitFailed"));
  }

  // Error side effects
  if (eventType === "error") {
    ctx.setConnectionStatus("disconnected");
    ctx.setIsInitializingSandbox(false);
    ctx.options?.onClearApprovals?.();
  }
}

// ---- Events handled outside processMessageEvent ----

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

function handleError(
  data: EventData,
  messageId: string,
  ctx: EventHandlerContext,
  forceCancelled?: boolean,
): void {
  const errorMsg = data.error || i18n.t("chat.unknownError");
  const isCancelled = forceCancelled || data.type === "CancelledError";

  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      if (isCancelled) {
        return {
          ...m,
          isStreaming: false,
          cancelled: true,
          parts: clearAllLoadingStates(m.parts || []),
        };
      }
      return {
        ...m,
        content: i18n.t("chat.errorPrefix", { error: errorMsg }),
        isStreaming: false,
        parts: clearAllLoadingStates(m.parts || []),
      };
    }),
  );
  ctx.setConnectionStatus("disconnected");
  ctx.setIsInitializingSandbox(false);
  ctx.options?.onClearApprovals?.();
}

async function handleApprovalRequired(
  data: EventData,
  ctx: EventHandlerContext,
): Promise<void> {
  if (data.id && ctx.options?.onApprovalRequired) {
    try {
      const approval = await authFetch<{
        status: string;
        message?: string;
        type?: string;
        fields?: FormField[];
        expires_at?: string | null;
      }>(`/human/${data.id}`);
      if (!approval) return;
      if (approval && approval.status === "pending") {
        ctx.options?.onApprovalRequired?.({
          id: data.id!,
          message: approval.message || "",
          type: approval.type || "form",
          fields: approval.fields || [],
          expires_at: approval.expires_at || null,
          timeout: (data as Record<string, unknown>).timeout as
            | number
            | undefined,
        });
      }
    } catch (err) {
      console.warn("[SSE] Failed to check approval status:", err);
    }
  }
}
