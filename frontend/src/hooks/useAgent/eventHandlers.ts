/**
 * Stream event handlers for useAgent hook
 * Handles all incoming SSE events and updates messages accordingly.
 *
 * Message transformation logic is unified in processMessageEvent (messageParts.ts).
 * This file handles: SSE parsing, duplicate detection, subagent stack management,
 * and React state updates (side effects).
 */

import type { Message, MessagePart } from "../../types";
import { uuid } from "../../utils/uuid";
import { sessionApi } from "../../services/api/session";
import i18n from "../../i18n";
import { translateApiError } from "../../utils/backendErrors";
import { parseDate } from "../../utils/datetime";
import type {
  StreamEvent,
  EventData,
  SubagentStackItem,
  UseAgentOptions,
} from "./types";
import { clearAllLoadingStates, createToolPart } from "./messageParts";
import { splitAssistantTurn } from "./steerTurnSplit";
import { convertAttachments, processMessageEvent } from "./eventProcessor";
import { dispatchToolMutationRefresh } from "../../components/chat/ChatMessage/items/toolMutationEvents";

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
  currentRunIdRef?: React.MutableRefObject<string | null>;
  setCurrentRunId?: (runId: string | null) => void;
  setSessionId: (id: string) => void;
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  markSteerDelivered?: (content: string, messageId?: string) => void;
  setConnectionStatus: (status: string) => void;
  setIsInitializingSandbox: (loading: boolean) => void;
  setSandboxError: (error: string | null) => void;
  setActiveGoal: React.Dispatch<
    React.SetStateAction<import("./types").ActiveGoalSpec | null>
  >;
  setGoalsByRunId: React.Dispatch<
    React.SetStateAction<Record<string, import("./types").ActiveGoalSpec>>
  >;
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
    const eventTime = parseDate(eventTimestamp);
    const historyTime = ctx.lastHistoryTimestampRef.current;
    if (eventTime < historyTime) {
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
  if (eventTimestamp) {
    const eventTime = parseDate(eventTimestamp);
    const previousTime = ctx.lastHistoryTimestampRef.current;
    if (!previousTime || eventTime > previousTime) {
      ctx.lastHistoryTimestampRef.current = eventTime;
    }
  }

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

  // A late event from a previous run must never resurrect an optimistic steer
  // after the user switched sessions or started a new turn.
  if (
    eventType === "steer:message" &&
    data.run_id &&
    ctx.currentRunIdRef?.current &&
    data.run_id !== ctx.currentRunIdRef.current
  ) {
    return;
  }

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

    case "goal:start": {
      ctx.setActiveGoal((prev) => {
        const goal: import("./types").ActiveGoalSpec = {
          objective: data.goal?.objective ?? prev?.objective ?? "",
          rubric: data.goal?.rubric ?? prev?.rubric,
          started_at: data.started_at ?? prev?.started_at,
        };
        if (data.run_id) goal.runId = data.run_id;
        else if (prev?.runId) goal.runId = prev.runId;
        if (data.goal?.max_iterations != null)
          goal.max_iterations = data.goal.max_iterations;
        else if (prev?.max_iterations != null)
          goal.max_iterations = prev.max_iterations;
        return goal;
      });
      if (data.run_id) {
        ctx.setGoalsByRunId((prev) => ({
          ...prev,
          [data.run_id!]: {
            objective:
              data.goal?.objective ?? prev[data.run_id!]?.objective ?? "",
            rubric: data.goal?.rubric ?? prev[data.run_id!]?.rubric,
            ...(data.goal?.max_iterations != null
              ? { max_iterations: data.goal.max_iterations }
              : prev[data.run_id!]?.max_iterations != null
                ? { max_iterations: prev[data.run_id!]!.max_iterations }
                : {}),
            runId: data.run_id,
            started_at: data.started_at ?? prev[data.run_id!]?.started_at,
          },
        }));
      }
      return;
    }

    case "goal:end": {
      ctx.setActiveGoal((prev) => {
        const goal: import("./types").ActiveGoalSpec = {
          objective: data.goal?.objective ?? prev?.objective ?? "",
          rubric: data.goal?.rubric ?? prev?.rubric,
          started_at: data.started_at ?? prev?.started_at,
          ended_at: data.ended_at,
        };
        if (data.run_id) goal.runId = data.run_id;
        else if (prev?.runId) goal.runId = prev.runId;
        if (data.goal?.max_iterations != null)
          goal.max_iterations = data.goal.max_iterations;
        else if (prev?.max_iterations != null)
          goal.max_iterations = prev.max_iterations;
        return goal;
      });
      if (data.run_id) {
        ctx.setGoalsByRunId((prev) => ({
          ...prev,
          [data.run_id!]: {
            objective:
              data.goal?.objective ?? prev[data.run_id!]?.objective ?? "",
            rubric: data.goal?.rubric ?? prev[data.run_id!]?.rubric,
            ...(data.goal?.max_iterations != null
              ? { max_iterations: data.goal.max_iterations }
              : prev[data.run_id!]?.max_iterations != null
                ? { max_iterations: prev[data.run_id!]!.max_iterations }
                : {}),
            runId: data.run_id,
            started_at: data.started_at ?? prev[data.run_id!]?.started_at,
            ended_at: data.ended_at ?? prev[data.run_id!]?.ended_at,
          },
        }));
      }
      // Auto-dismiss the goal chip after a short delay so the user sees
      // the completed state briefly before it disappears.
      setTimeout(() => ctx.setActiveGoal(null), 2000);
      return;
    }

    case "user:message": {
      handleUserMessage(data, messageId, eventTimestamp, ctx);
      return;
    }

    case "steer:message": {
      const steerContent =
        typeof data.content === "string" ? data.content.trim() : "";
      const steerAttachments = convertAttachments(data.attachments);
      const deliveredSteerId =
        typeof data.message_id === "string" && data.message_id.trim()
          ? data.message_id
          : `steer-${eventId}`;
      // 插话送达：先封存当前助手轮次，再把事件本身落入 messages。
      // 这样即使 SSE 重连时本地 optimistic 状态已丢失，消息仍会立即可见，
      // 并且后续历史回放与实时状态使用同一条数据源。
      ctx.setMessages((prev) => {
        const splitMessages = splitAssistantTurn(prev, messageId);
        if (!steerContent) return splitMessages;
        const hasOptimisticById = splitMessages.some(
          (message) =>
            message.id === deliveredSteerId &&
            message.metadata?.queued === true,
        );
        const alreadyPresent = splitMessages.some((message) =>
          typeof data.message_id === "string" && data.message_id.trim()
            ? message.id === deliveredSteerId
            : message.role === "user" &&
              message.content === steerContent &&
              message.metadata?.steer === true &&
              message.metadata?.queued !== true,
        );
        let removedOptimistic = false;
        const withoutOptimistic = splitMessages.filter((message) => {
          const isOptimistic =
            message.role === "user" &&
            message.metadata?.steer === true &&
            message.metadata?.queued === true &&
            (message.id === deliveredSteerId ||
              (!hasOptimisticById && message.content === steerContent));
          if (isOptimistic && !removedOptimistic) {
            removedOptimistic = true;
            return false;
          }
          return true;
        });
        if (alreadyPresent) return withoutOptimistic;
        const delivered = {
          id: deliveredSteerId,
          role: "user" as const,
          content: steerContent,
          attachments: steerAttachments,
          // created_at 是用户发送时刻；事件信封时间（注入时刻）只作回退
          timestamp:
            typeof data.created_at === "string"
              ? parseDate(data.created_at)
              : eventTimestamp
                ? parseDate(eventTimestamp)
                : new Date(),
          runId: data.run_id,
          metadata: { steer: true, queued: false },
        };
        // splitAssistantTurn leaves a fresh assistant placeholder for the
        // response after this steer. Insert before it so the visual order is
        // assistant turn → steer → next assistant turn.
        const nextAssistantIndex = withoutOptimistic.findIndex(
          (message) => message.id === messageId && message.role === "assistant",
        );
        if (nextAssistantIndex === -1) return [...withoutOptimistic, delivered];
        return [
          ...withoutOptimistic.slice(0, nextAssistantIndex),
          delivered,
          ...withoutOptimistic.slice(nextAssistantIndex),
        ];
      });
      if (steerContent) {
        ctx.markSteerDelivered?.(steerContent, deliveredSteerId);
      }
      return;
    }

    case "user:cancel": {
      handleError(data, messageId, ctx, true, { keepConnectionOpen: true });
      return;
    }

    case "run:resumed": {
      // 系统中断后同 run 无缝续跑：清空气泡里的半截输出/错误/取消状态，
      // 回到流式空态接收重新生成的完整回答（模型会重跑这一轮）。
      ctx.setMessages((prev) => {
        const reset = {
          parts: [],
          content: "",
          toolCalls: [],
          cancelled: false,
          isStreaming: true,
        };
        if (prev.some((message) => message.id === messageId)) {
          return prev.map((message) =>
            message.id === messageId ? { ...message, ...reset } : message,
          );
        }
        return [
          ...prev,
          {
            id: messageId,
            role: "assistant" as const,
            timestamp: new Date(),
            runId: typeof data.run_id === "string" ? data.run_id : undefined,
            ...reset,
          },
        ];
      });
      return;
    }

    case "complete":
    case "done": {
      ctx.setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? {
                ...m,
                isStreaming: false,
                parts: clearAllLoadingStates(m.parts || [], {
                  preserveAskHuman: true,
                }),
              }
            : m,
        ),
      );
      ctx.setConnectionStatus("disconnected");
      // AI 回复完成，用户正在查看当前 session，立即标记为已读
      const activeSessionId = ctx.sessionIdRef.current;
      if (activeSessionId) {
        sessionApi.markRead(activeSessionId).catch(() => {});
      }
      ctx.options?.onStreamDone?.();
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
      appendAskHumanToolPart(data, messageId, eventTimestamp, ctx);
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
    "tool:args:chunk",
    "approval_resolved",
    "artifact:result",
    "sandbox:starting",
    "sandbox:ready",
    "sandbox:error",
    "token:usage",
    "todo:updated",
    "summary",
    "recommend:questions",
    "followup:questions",
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

  if (eventType === "tool:result" && data.success !== false) {
    dispatchToolMutationRefresh(data.result);
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
    ctx.options?.onClearApprovals?.(ctx.sessionIdRef.current);
  }
}

// ---- Events handled outside processMessageEvent ----

function handleUserMessage(
  data: EventData,
  messageId: string,
  eventTimestamp: string | undefined,
  ctx: EventHandlerContext,
): void {
  const extractOptimisticContent = (content: string): string | null => {
    const match = content.match(/^\[[^\]]+\]\s([\s\S]*)$/);
    return match ? match[1] : null;
  };
  const resolvedMessageId =
    typeof data.message_id === "string" && data.message_id.trim()
      ? data.message_id
      : typeof data.run_id === "string" && data.run_id.trim()
        ? `${data.run_id}:user`
        : uuid();
  const userContent = data.content || "";
  const userAttachments = convertAttachments(data.attachments) || [];
  const enabledSkills = Array.isArray(data.enabled_skills)
    ? data.enabled_skills
    : undefined;
  const runId =
    typeof data.run_id === "string" && data.run_id.trim()
      ? data.run_id
      : undefined;

  if (userContent) {
    ctx.setMessages((prev) => {
      let existingUserIndex = prev.findIndex(
        (candidate) =>
          candidate.role === "user" &&
          (candidate.id === resolvedMessageId ||
            (runId != null && candidate.runId === runId)),
      );
      if (existingUserIndex === -1) {
        // 乐观用户消息总在列表尾部；从头扫描会在重发相同内容时
        // 误命中上一轮的同内容消息，把流式助手插到旧消息下面。
        for (let index = prev.length - 1; index >= 0; index -= 1) {
          const candidate = prev[index];
          if (
            candidate?.role === "user" &&
            candidate.content === userContent
          ) {
            existingUserIndex = index;
            break;
          }
        }
      }

      const optimisticContent = extractOptimisticContent(userContent);
      if (existingUserIndex === -1 && optimisticContent) {
        for (let index = prev.length - 1; index >= 0; index -= 1) {
          const candidate = prev[index];
          if (
            candidate?.role === "user" &&
            candidate.content === optimisticContent
          ) {
            existingUserIndex = index;
            break;
          }
        }
      }

      const messagesWithoutTarget = prev.filter(
        (candidate) =>
          !(candidate.role === "assistant" && candidate.id === messageId),
      );
      const existingTarget = prev.find(
        (candidate) =>
          candidate.role === "assistant" && candidate.id === messageId,
      );
      let userMessage: Message;
      if (existingUserIndex !== -1) {
        const existingUser = prev[existingUserIndex];
        userMessage = {
          ...existingUser,
          content: userContent,
          runId: runId ?? existingUser.runId,
          attachments:
            userAttachments.length > 0
              ? userAttachments
              : existingUser.attachments,
          enabledSkills,
        };
        const indexWithoutTarget = messagesWithoutTarget.findIndex(
          (candidate) => candidate.id === existingUser.id,
        );
        messagesWithoutTarget[indexWithoutTarget] = userMessage;
      } else {
        userMessage = {
          id: resolvedMessageId,
          role: "user",
          content: userContent,
          timestamp: eventTimestamp ? parseDate(eventTimestamp) : new Date(),
          attachments: userAttachments,
          enabledSkills,
          runId,
        };
        const streamingAssistantIndex = messagesWithoutTarget.findIndex(
          (candidate) =>
            candidate.role === "assistant" && candidate.isStreaming,
        );
        const insertionIndex =
          streamingAssistantIndex === -1
            ? messagesWithoutTarget.length
            : streamingAssistantIndex;
        messagesWithoutTarget.splice(insertionIndex, 0, userMessage);
      }

      const assistant: Message = existingTarget
        ? {
            ...existingTarget,
            isStreaming: true,
            runId: runId ?? existingTarget.runId,
          }
        : {
            id: messageId,
            role: "assistant",
            content: "",
            timestamp: eventTimestamp ? parseDate(eventTimestamp) : new Date(),
            parts: [],
            isStreaming: true,
            runId,
          };
      const userIndex = messagesWithoutTarget.findIndex(
        (candidate) => candidate.id === userMessage.id,
      );
      messagesWithoutTarget.splice(userIndex + 1, 0, assistant);
      return messagesWithoutTarget;
    });
  }
}

function handleError(
  data: EventData,
  messageId: string,
  ctx: EventHandlerContext,
  forceCancelled?: boolean,
  options?: { keepConnectionOpen?: boolean },
): void {
  const errorMsg = data.error
    ? translateApiError(data.code, data.error, undefined, i18n.t.bind(i18n))
    : i18n.t("chat.unknownError");
  const isCancelled = forceCancelled || data.type === "CancelledError";

  ctx.setMessages((prev) =>
    prev.map((m) => {
      if (m.id !== messageId) return m;
      if (isCancelled) {
        return {
          ...m,
          isStreaming: false,
          cancelled: true,
          parts: appendCancelledPart(clearAllLoadingStates(m.parts || [])),
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
  if (!options?.keepConnectionOpen) {
    ctx.setConnectionStatus("disconnected");
    ctx.setIsInitializingSandbox(false);
  }
  ctx.options?.onClearApprovals?.(ctx.sessionIdRef.current);
}

function appendCancelledPart(parts: MessagePart[]): MessagePart[] {
  if (parts.some((part) => part.type === "cancelled")) {
    return parts;
  }
  return [...parts, { type: "cancelled" }];
}

function appendAskHumanToolPart(
  data: EventData,
  messageId: string,
  eventTimestamp: string | undefined,
  ctx: EventHandlerContext,
): void {
  const toolCallId = data.tool_call_id || data.id;
  const args = {
    message: data.message || "",
    fields: data.fields || [],
  };
  const toolPart = createToolPart(
    "ask_human",
    args,
    data.depth || 0,
    data.agent_id,
    toolCallId,
    eventTimestamp,
  );

  ctx.setMessages((prev) => {
    const existing = prev.find((message) => message.id === messageId);
    if (existing) {
      if (
        existing.parts?.some(
          (part) =>
            part.type === "tool" &&
            part.name === "ask_human" &&
            part.id === toolCallId,
        )
      ) {
        return prev;
      }
      return prev.map((message) =>
        message.id === messageId
          ? { ...message, parts: [...(message.parts || []), toolPart] }
          : message,
      );
    }
    return [
      ...prev,
      {
        id: messageId,
        role: "assistant",
        content: "",
        timestamp: eventTimestamp ? parseDate(eventTimestamp) : new Date(),
        parts: [toolPart],
        isStreaming: true,
      },
    ];
  });
}

function handleApprovalRequired(
  data: EventData,
  ctx: EventHandlerContext,
): void {
  if (!data.id || !ctx.options?.onApprovalRequired) return;

  // The SSE event is emitted after the approval is created and already carries
  // the complete form payload. Render it immediately instead of making the UI
  // depend on a second request which can race storage replication or auth refresh.
  ctx.options.onApprovalRequired({
    id: data.id,
    message: data.message || "",
    type: data.type || "form",
    fields: data.fields || [],
    expires_at: data.expires_at || null,
    metadata:
      data.metadata || (data.interrupt_id ? { mode: "interrupt" } : undefined),
  });
}
