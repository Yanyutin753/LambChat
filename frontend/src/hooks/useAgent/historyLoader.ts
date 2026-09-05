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
import { clearAllLoadingStates, createToolPart } from "./messageParts";
import { markInterruptedBySteer } from "./steerTurnSplit";
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
  /** 审批状态查询回调：无论 pending 与否都会收到，用于补收尾历史幽灵 pill。 */
  onApprovalLookup?: (approval: {
    id: string;
    status: string;
    metadata?: Record<string, unknown> | null;
  }) => void;
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

const STEER_REPLY_TEXT_EVENTS = new Set(["thinking", "message:chunk"]);

/**
 * 旧版后端把 steer:message 事件写在模型调用成功之后，事件落在 run 尾部
 * 且不带 created_at，直接按序重建会把插话渲染在它自己的回答之后。
 * 重建前把这类事件（组）移回其回答文本轮次之前：向前跳过同 run 的连续
 * 文本事件（thinking / message:chunk），插到该文本块开始处。带
 * created_at 的新版事件按注入时刻写入，位置天然正确，直接跳过。
 */
function anchorLegacySteerMessageEvents(events: HistoryEvent[]): HistoryEvent[] {
  const anchored = [...events];
  for (let i = 0; i < anchored.length; i += 1) {
    const event = anchored[i];
    if (event.event_type !== "steer:message") continue;
    const data = event.data as HistoryEventData | null | undefined;
    if (data && typeof data.created_at === "string") continue;

    // 连续多条插话一起移动，保持相对顺序
    let groupEnd = i;
    while (
      groupEnd + 1 < anchored.length &&
      anchored[groupEnd + 1].event_type === "steer:message" &&
      anchored[groupEnd + 1].run_id === event.run_id
    ) {
      groupEnd += 1;
    }

    let anchor = i;
    while (
      anchor - 1 >= 0 &&
      anchored[anchor - 1].run_id === event.run_id &&
      STEER_REPLY_TEXT_EVENTS.has(anchored[anchor - 1].event_type)
    ) {
      anchor -= 1;
      // thinking 通常开启一次模型调用：把插话放到回答轮次的 thinking
      // 之前即停止，不越过轮次边界吞并上一轮的纯文本
      if (anchored[anchor].event_type === "thinking") {
        break;
      }
    }
    if (anchor === i) continue;

    const group = anchored.splice(i, groupEnd - i + 1);
    anchored.splice(anchor, 0, ...group);
    i = anchor + group.length - 1;
  }
  return anchored;
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
  messageIdOverride?: string,
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
      tool_call_id?: string;
      message?: string;
      type?: string;
      fields?: FormField[];
    };
    if (!currentAssistantMessage) {
      currentAssistantMessage = {
        id: messageIdOverride || event.run_id || uuid(),
        role: "assistant",
        content: "",
        timestamp: parseEventTimestamp(event.timestamp, Date.now()),
        parts: [],
        isStreaming: false,
        runId: event.run_id,
      };
    }
    // approval_required.id is the persisted approval id; resolution events
    // identify the tool part by tool_call_id. Keep the tool part keyed by the
    // latter so historical approvals resolve exactly like live events.
    const toolCallId = approvalData.tool_call_id || approvalData.id;
    if (
      toolCallId &&
      !currentAssistantMessage.parts?.some(
        (part) => part.type === "tool" && part.id === toolCallId,
      )
    ) {
      currentAssistantMessage = {
        ...currentAssistantMessage,
        parts: [
          ...(currentAssistantMessage.parts || []),
          createToolPart(
            "ask_human",
            {
              message: approvalData.message || "",
              fields: approvalData.fields || [],
            },
            eventData.depth || 0,
            eventData.agent_id,
            toolCallId,
            event.timestamp,
          ),
        ],
      };
    }
    if (
      approvalData.id &&
      (opts.options?.onApprovalRequired || opts.onApprovalLookup)
    ) {
      authFetch<{
        id?: string;
        status: string;
        message?: string;
        type?: string;
        fields?: FormField[];
        metadata?: Record<string, unknown>;
      }>(buildApiUrl(`/human/${approvalData.id}`))
        .then((data) => data ?? null)
        .then((approval) => {
          if (approval?.id) {
            // 无论 pending 与否都上报：已决的 scheduled-task 审批要在此
            // 补收尾历史幽灵 pill（旧版事件没有 approval_resolved 可回放）
            opts.onApprovalLookup?.({
              id: approval.id,
              status: approval.status,
              metadata: approval.metadata ?? null,
            });
          }
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
    const messageId = messageIdOverride || event.run_id || uuid();
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
 * 为缺失 run_id 的历史事件回填就近 run_id。
 * 旧记录（如推荐问题）可能缺少 run_id 信封；按时间序取前向最近的
 * run_id，无前向时回退到后向第一个 run_id，保持与逐事件反向查找一致的语义。
 */
/**
 * 中断后同 run 无缝续跑：丢弃半截/错误累积，同一气泡回到空态，
 * 后续事件（模型重新生成的完整回答）从零重新折叠。
 */
function resetInterruptedAssistantForResume(
  message: Message | null,
): Message | null {
  if (!message) return null;
  return {
    ...message,
    parts: [],
    content: "",
    toolCalls: [],
    cancelled: false,
  };
}

export function normalizeEventRunIds(events: HistoryEvent[]): HistoryEvent[] {
  const prevRunIdByIndex: Array<string | undefined> = new Array(
    events.length,
  );
  let lastSeenRunId: string | undefined;
  for (let index = 0; index < events.length; index++) {
    prevRunIdByIndex[index] = lastSeenRunId;
    const runId = events[index].run_id;
    if (runId) lastSeenRunId = runId;
  }

  const nextRunIdByIndex: Array<string | undefined> = new Array(
    events.length,
  );
  let nextSeenRunId: string | undefined;
  for (let index = events.length - 1; index >= 0; index--) {
    nextRunIdByIndex[index] = nextSeenRunId;
    const runId = events[index].run_id;
    if (runId) nextSeenRunId = runId;
  }

  return events.map((event, index) => {
    if (event.run_id) return event;
    const runId = prevRunIdByIndex[index] || nextRunIdByIndex[index];
    return runId ? { ...event, run_id: runId } : event;
  });
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
  // Older/synthesized history records (notably recommended questions) may
  // omit the envelope run_id even though the surrounding trace has one. Keep
  // those events in the same assistant turn instead of creating an orphan
  // message with an undefined run id.
  const normalizedEvents = normalizeEventRunIds(sortedEvents);

  const anchoredEvents = anchorLegacySteerMessageEvents(normalizedEvents);

  const reconstructedMessages: Message[] = [];
  // run 内每完成一个 assistant 轮次（入列）计数一次，替代循环内对
  // reconstructedMessages 的全量 filter（长会话 O(n²) 热点）
  const assistantTurnCountsByRunId = new Map<string, number>();
  const pushMessage = (message: Message) => {
    reconstructedMessages.push(message);
    if (message.role === "assistant" && message.runId) {
      assistantTurnCountsByRunId.set(
        message.runId,
        (assistantTurnCountsByRunId.get(message.runId) || 0) + 1,
      );
    }
  };
  let currentAssistantMessage: Message | null = null;
  const seenUserMessageIds = new Set<string>();
  const seenUserMessageRunIds = new Set<string>();
  const seenSteerMessageIds = new Set<string>();

  for (const event of anchoredEvents) {
    const eventType = event.event_type;
    const eventData = event.data as HistoryEventData;

    // Handle steer message separately（独立事件，不参与用户消息去重）
    if (eventType === "steer:message") {
      if (currentAssistantMessage) {
        // 插话即打断：封存的前一段回答标记「已停止」，与实时分割视觉一致
        pushMessage(markInterruptedBySteer(currentAssistantMessage));
        currentAssistantMessage = null;
      }
      const steerData = eventData as HistoryEventData & {
        content?: string;
        message_id?: string;
      };
      const steerId =
        typeof steerData.message_id === "string" && steerData.message_id.trim()
          ? steerData.message_id
          : `steer-h-${sortedEvents.indexOf(event)}`;
      // 模型调用失败后消息原 ID 回队，重试送达会再次写出同
      // message_id 事件；按 ID 去重只渲染第一次（即用户发送位置）
      if (
        typeof steerData.message_id === "string" &&
        steerData.message_id.trim() &&
        seenSteerMessageIds.has(steerId)
      ) {
        continue;
      }
      seenSteerMessageIds.add(steerId);
      pushMessage({
        id: steerId,
        role: "user",
        content: steerData.content || "",
        attachments: convertAttachments(steerData.attachments),
        timestamp:
          typeof steerData.created_at === "string"
            ? parseEventTimestamp(steerData.created_at, Date.now())
            : parseEventTimestamp(event.timestamp, Date.now()),
        runId: event.run_id,
        metadata: { steer: true },
      });
      continue;
    }

    // Handle user message separately
    if (eventType === "user:message") {
      const userMessageId = resolveUserMessageId(event, eventData);
      const userMessageRunId =
        typeof event.run_id === "string" && event.run_id.trim()
          ? event.run_id
          : null;
      // run 级去重用于压制同 run 的重复回放（不同 id 的重复消息）；
      // 插话消息（steer-* 前缀，由注入时生成）与首条用户消息同 run
      // 但不是重复，不参与 run 级去重
      const isSteerMessage = userMessageId.startsWith("steer-");
      if (
        seenUserMessageIds.has(userMessageId) ||
        (!isSteerMessage &&
          userMessageRunId != null &&
          seenUserMessageRunIds.has(userMessageRunId))
      ) {
        continue;
      }
      seenUserMessageIds.add(userMessageId);
      if (!isSteerMessage && userMessageRunId) {
        seenUserMessageRunIds.add(userMessageRunId);
      }

      if (currentAssistantMessage) {
        pushMessage(currentAssistantMessage);
        currentAssistantMessage = null;
      }
      const userAttachments = convertAttachments(eventData.attachments);
      const enabledSkills = Array.isArray(eventData.enabled_skills)
        ? eventData.enabled_skills
        : undefined;
      const runModes = Array.isArray(eventData.run_modes)
        ? eventData.run_modes.filter(
            (mode): mode is "auto" | "goal" =>
              mode === "auto" || mode === "goal",
          )
        : undefined;
      pushMessage({
        id: userMessageId,
        role: "user",
        content: eventData.content || "",
        timestamp: parseEventTimestamp(event.timestamp, Date.now()),
        attachments: userAttachments,
        runId: event.run_id,
        enabledSkills,
        runModes,
      });
      continue;
    }

    // Handle user cancel
    if (eventType === "user:cancel") {
      // reason=steer：插话打断 ask_human 挂起。已停止是状态行文字切换
      // （cancelled 标志 → RunStepsCollapse「已停止」），不追加已取消胶囊。
      const steerInterrupted = eventData.reason === "steer";
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
          parts: steerInterrupted
            ? updatedParts
            : [...updatedParts, { type: "cancelled" as const }],
        };
        pushMessage(updatedMessage);
      } else if (!steerInterrupted) {
        pushMessage({
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

    // Handle seamless run resume
    if (eventType === "run:resumed") {
      // 中断后同 run 恢复：丢弃半截/错误累积，同一气泡从空态继续折叠
      // 后续事件（模型重新生成完整回答）
      currentAssistantMessage = resetInterruptedAssistantForResume(
        currentAssistantMessage,
      );
      continue;
    }

    if (
      !currentAssistantMessage &&
      canAttachEventTypeToPreviousAssistant(eventType)
    ) {
      const lastMessageIndex = reconstructedMessages.length - 1;
      const lastMessage = reconstructedMessages[lastMessageIndex];
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
      !currentAssistantMessage && event.run_id
        ? (() => {
            const priorAssistantTurns =
              assistantTurnCountsByRunId.get(event.run_id as string) || 0;
            return priorAssistantTurns === 0
              ? event.run_id
              : `${event.run_id}#t${priorAssistantTurns}`;
          })()
        : undefined,
    );
  }

  if (currentAssistantMessage) {
    pushMessage(currentAssistantMessage);
  }

  // 无终态事件的 run（中断后未恢复/旧数据）不允许留下"执行中"部件：
  // 静默停转半截工具/参数流/思考/子代理的 loading（内容保留），避免历史里
  // 永远转圈。终态判定在折叠完成后统一进行，steer 封存的中间轮次也能等到
  // 自己 run 的 done；有终态的 run 完全不动。
  const settledRunIds = new Set<string>();
  for (const event of anchoredEvents) {
    if (
      event.run_id &&
      (event.event_type === "done" ||
        event.event_type === "complete" ||
        event.event_type === "error" ||
        event.event_type === "user:cancel")
    ) {
      settledRunIds.add(event.run_id);
    }
  }
  for (let index = 0; index < reconstructedMessages.length; index += 1) {
    const message = reconstructedMessages[index];
    if (
      message.role === "assistant" &&
      message.runId &&
      !settledRunIds.has(message.runId)
    ) {
      reconstructedMessages[index] = {
        ...message,
        // ask_human 卡片保持待响应：HITL 挂起中的 run 同样没有终态事件，
        // 但审批卡必须继续可交互（恢复走审批响应路径，不走无缝续跑）
        parts: clearAllLoadingStates(message.parts || [], {
          preserveAskHuman: true,
        }),
      };
    }
  }

  // Some runs emit lifecycle events (for example `agent:start`) without ever
  // producing assistant content. They still create a placeholder while the
  // event stream is being folded, which leaves an empty assistant bubble in
  // history between two real turns. Keep meaningful terminal/tool states, but
  // remove content-less placeholders before the list reaches the UI.
  return reconstructedMessages.filter((message) => {
    if (message.role !== "assistant") return true;
    return Boolean(
      message.content?.trim() ||
        message.parts?.length ||
        message.toolCalls?.length ||
        message.toolResults?.length ||
        message.cancelled,
    );
  });
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

  const hasRunUser = messagesWithPendingUser.some(
    (message) => message.role === "user" && message.runId === runId,
  );
  if (!hasRunUser) {
    return {
      streamingMessageId: existingAssistant?.id ?? createId(),
      messages: messagesWithPendingUser.filter(
        (message) => !(message.role === "assistant" && message.runId === runId),
      ),
    };
  }

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

/**
 * 补收尾历史幽灵 ask_human pill：scheduled_task_create 的确认审批
 * （approval_required 事件）会生成 ask_human pill，但工具结果带的是
 * scheduled_task_create 自己的 tool_call_id，pill 永远停在「加载中」。
 * 新版后端会写 approval_resolved 事件；旧数据靠审批终态查询在此兜底。
 */
export function resolveLegacyScheduledTaskApproval(
  messages: Message[],
  approval: {
    id: string;
    status: string;
    metadata?: Record<string, unknown> | null;
  },
): Message[] {
  if (
    !approval?.id ||
    approval.status === "pending" ||
    approval.metadata?.approval_type !== "scheduled_task_create"
  ) {
    return messages;
  }

  const approved = approval.status === "approved";
  const resultStatus = approved
    ? "success"
    : approval.status === "expired" || approval.status === "timeout"
      ? "timeout"
      : "rejected";

  let changed = false;
  const next = messages.map((message) => {
    const hasPhantom = message.parts?.some(
      (part) =>
        part.type === "tool" &&
        part.name === "ask_human" &&
        part.id === approval.id &&
        part.isPending,
    );
    if (!hasPhantom) return message;
    changed = true;
    return {
      ...message,
      parts: message.parts?.map((part) =>
        part.type === "tool" &&
        part.name === "ask_human" &&
        part.id === approval.id &&
        part.isPending
          ? {
              ...part,
              isPending: false,
              success: approved,
              result: {
                status: resultStatus,
                message: `Scheduled task creation ${approval.status}.`,
                values: {},
              },
            }
          : part,
      ),
    };
  });
  return changed ? next : messages;
}

/** 构造 onApprovalLookup 回调：查到已决 scheduled-task 审批时补收尾幽灵 pill。 */
export function createScheduledTaskApprovalLookup(
  setMessages: (updater: (previous: Message[]) => Message[]) => void,
) {
  return (approval: {
    id: string;
    status: string;
    metadata?: Record<string, unknown> | null;
  }) => setMessages((previous) => resolveLegacyScheduledTaskApproval(previous, approval));
}
