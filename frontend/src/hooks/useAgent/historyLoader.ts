import { isScheduledResult, mergeScheduledResult } from "./scheduledResults";
/**
 * History event loader for useAgent hook
 * Reconstructs messages from stored events.
 *
 * Message transformation logic is unified in processMessageEvent (messageParts.ts).
 * This file handles: event iteration, message reconstruction, and
 * user:message / user:cancel / approval_required which are history-specific.
 */

import {
  anchorLegacySteerMessageEvents,
  normalizeEventRunIds,
} from "./historyEventOrdering";
export { normalizeEventRunIds } from "./historyEventOrdering";
import { HistoryPartReplay, HistoryReplayStack } from "./historyReplayParts";
import { getGoalProjectionIdentity } from "./goalControlScope";
import type { Message, MessagePart, FormField } from "../../types";
import type { SessionApprovalStatus } from "../../types/session";
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
import {
  convertAttachments,
  isCancelledErrorType,
  processMessageEvent,
} from "./eventProcessor";
import {
  clearAllLoadingStates,
  createToolPart,
  isSandboxConfirmApprovalEvent,
} from "./messageParts";
import { assistantMessageHasContent } from "./settleStream";
import { sealAssistantBeforeSteer } from "./steerTurnSplit";
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
  streaming?: boolean;
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
  approvalStatuses?: Record<string, SessionApprovalStatus>;
  isCurrent?: () => boolean;
  partReplay?: HistoryPartReplay;
  replayStack?: HistoryReplayStack;
  resolvedApprovalIds?: ReadonlySet<string>;
  queriedApprovalIds?: Set<string>;
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
  const storedData = event.data as HistoryEventData;
  const eventData = {
    ...storedData,
    timestamp: storedData.timestamp ?? event.timestamp,
  };
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
  if (eventType === "metadata" || eventType === "goal:updated") {
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
      /** sandbox_confirm = 沙箱确认门（服务端 origin 标记）：执行卡 +
       * 审批面板已完整表达，不合成 ask_human 工具卡（避免一次执行双卡） */
      origin?: string;
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
    // 沙箱确认门（origin=sandbox_confirm）：执行卡（等待确认→结果）+
    // 审批面板已完整表达，不合成 ask_human 工具卡（避免一次执行双卡）；
    // 常规审批（ask_human/定时任务）保持合成，历史回放与直播共用判定。
    // approval_required.id is the persisted approval id; resolution events
    // identify the tool part by tool_call_id. Keep the tool part keyed by the
    // latter so historical approvals resolve exactly like live events.
    const toolCallId = approvalData.tool_call_id || approvalData.id;
    if (!isSandboxConfirmApprovalEvent(approvalData) && toolCallId) {
      const create = () =>
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
        );
      if (opts.partReplay)
        opts.partReplay.ensureApproval(
          currentAssistantMessage,
          toolCallId,
          create,
        );
      else if (
        !currentAssistantMessage.parts?.some(
          (part) => part.type === "tool" && part.id === toolCallId,
        )
      ) {
        currentAssistantMessage = {
          ...currentAssistantMessage,
          parts: [...(currentAssistantMessage.parts || []), create()],
        };
      }
    }
    const prefetched =
      approvalData.id &&
      opts.approvalStatuses &&
      Object.hasOwn(opts.approvalStatuses, approvalData.id)
        ? opts.approvalStatuses[approvalData.id]
        : undefined;
    if (prefetched && !opts.resolvedApprovalIds?.has(prefetched.id)) {
      if (opts.partReplay)
        opts.partReplay.repairApproval(
          currentAssistantMessage,
          prefetched,
          resolveLegacyScheduledTaskApproval,
        );
      else
        currentAssistantMessage = resolveLegacyScheduledTaskApproval(
          [currentAssistantMessage],
          prefetched,
        )[0];
    }
    if (
      approvalData.id &&
      !opts.resolvedApprovalIds?.has(approvalData.id) &&
      !opts.queriedApprovalIds?.has(approvalData.id) &&
      (opts.options?.onApprovalRequired || opts.onApprovalLookup)
    ) {
      opts.queriedApprovalIds?.add(approvalData.id);
      const approvalLookup = prefetched
        ? Promise.resolve(prefetched)
        : authFetch<SessionApprovalStatus>(
            buildApiUrl(`/human/${approvalData.id}`),
          );
      approvalLookup
        .then((data) => data ?? null)
        .then((approval) => {
          if (opts.isCurrent && !opts.isCurrent()) return;
          if (approval?.id) {
            // 无论 pending 与否都上报：已决的 scheduled-task 审批要在此
            // 补收尾历史幽灵 pill（旧版事件没有 approval_resolved 可回放）
            opts.onApprovalLookup?.({
              id: approval.id,
              status: approval.status,
              metadata: approval.metadata ?? null,
            });
          }
          if (
            approval?.status === "pending" &&
            (!opts.isCurrent || opts.isCurrent())
          ) {
            opts.options?.onApprovalRequired?.({
              id: approvalData.id!,
              message: approval.message || "",
              type: approval.type || "form",
              fields: approval.fields,
              metadata: approval.metadata ?? undefined,
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
    if (isCancelledErrorType(errorData.type) && !currentAssistantMessage) {
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

  // Materialize the ordered stack only when the shared fallback needs it.
  if (eventType === "agent:call") {
    opts.replayStack?.add({
      agent_id: agentId || "unknown",
      ...(eventData.agent_call_id
        ? { agent_call_id: eventData.agent_call_id }
        : {}),
      depth,
      message_id: msg.id,
    });
  }
  if (
    opts.partReplay?.replay(
      msg,
      eventType,
      eventData as EventData,
      agentId || (depth ? opts.replayStack?.latest(msg.id, depth) : undefined),
    )
  ) {
    if (eventType === "agent:result")
      opts.replayStack?.remove(
        agentId || "unknown",
        msg.id,
        eventData.agent_call_id,
      );
    return msg;
  }
  opts.partReplay?.flush(msg);
  opts.replayStack?.flush();

  // Use unified event processor
  const result = processMessageEvent(
    eventType,
    eventData as EventData,
    msg.parts || [],
    msg.content,
    msg.toolCalls || [],
    depth,
    opts.activeSubagentStack,
    Boolean(opts.streaming),
    msg.id,
  );

  // Apply result to message
  msg.parts = result.parts;
  msg.content = result.content;
  msg.toolCalls = result.toolCalls;

  if (result.toolResult) {
    (msg.toolResults ??= []).push(result.toolResult);
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

  if (eventType === "agent:result")
    opts.replayStack?.remove(
      agentId || "unknown",
      msg.id,
      eventData.agent_call_id,
    );

  return msg;
}

/**
 * 同 run 恢复保留已有内容，仅清理中断状态和悬挂的 loading。
 */
function resetInterruptedAssistantForResume(
  message: Message | null,
): Message | null {
  if (!message) return null;
  return {
    ...message,
    parts: clearAllLoadingStates(message.parts || []).filter(
      (part) => part.type !== "cancelled",
    ),
    cancelled: false,
  };
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

  // Concurrent old runs and delayed final events must not share an assistant builder.
  const eventsByRun = new Map<string | undefined, HistoryEvent[]>();
  for (const event of normalizedEvents) {
    const runEvents = eventsByRun.get(event.run_id);
    if (runEvents) runEvents.push(event);
    else eventsByRun.set(event.run_id, [event]);
  }
  if (eventsByRun.size > 1) {
    const messages: Message[] = [];
    opts.activeSubagentStack.length = 0;
    for (const runEvents of eventsByRun.values()) {
      const activeSubagentStack: SubagentStackItem[] = [];
      messages.push(
        ...reconstructMessagesFromEvents(runEvents, processedEventIds, {
          ...opts,
          activeSubagentStack,
        }),
      );
      opts.activeSubagentStack.push(...activeSubagentStack);
    }
    return messages.sort(
      (a, b) => a.timestamp.getTime() - b.timestamp.getTime(),
    );
  }

  const anchoredEvents = anchorLegacySteerMessageEvents(normalizedEvents);
  const sortedEventIndexes = new Map<HistoryEvent, number>();
  const resolvedApprovalIds = new Set<string>();
  sortedEvents.forEach((event, index) => {
    if (!sortedEventIndexes.has(event)) sortedEventIndexes.set(event, index);
    if (event.event_type === "approval_resolved") {
      const id = (event.data as HistoryEventData).id;
      if (typeof id === "string") resolvedApprovalIds.add(id);
    }
  });
  const replayOptions: ProcessHistoryOptions = {
    ...opts,
    resolvedApprovalIds,
    queriedApprovalIds: new Set(),
    partReplay: new HistoryPartReplay(Boolean(opts.streaming)),
    replayStack: new HistoryReplayStack(opts.activeSubagentStack),
  };

  const identities = new Map<
    string,
    NonNullable<Message["assistantIdentity"]>
  >();
  const reconstructedMessages: Message[] = [];
  const scheduledResults: import("./scheduledResults").ScheduledResult[] = [];
  // run 内每完成一个 assistant 轮次（入列）计数一次，替代循环内对
  // reconstructedMessages 的全量 filter（长会话 O(n²) 热点）
  const assistantTurnCountsByRunId = new Map<string, number>();
  const pushMessage = (message: Message) => {
    replayOptions.partReplay?.flush(message);
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
    if (eventType === "scheduled:result") {
      if (isScheduledResult(eventData)) scheduledResults.push(eventData);
      continue;
    }
    if (
      currentAssistantMessage &&
      event.run_id &&
      currentAssistantMessage.runId !== event.run_id &&
      ["goal:continuation", "goal:start"].includes(eventType)
    ) {
      pushMessage(currentAssistantMessage);
      currentAssistantMessage = null;
      replayOptions.replayStack?.clear();
    }
    if (eventType === "goal:continuation") continue;
    if (
      currentAssistantMessage &&
      ["steer:message", "user:message", "user:cancel", "run:resumed"].includes(
        eventType,
      )
    )
      replayOptions.partReplay?.flush(currentAssistantMessage);

    if (event.run_id && !eventData.depth) {
      if (eventData.assistant_identity) {
        identities.set(event.run_id, eventData.assistant_identity);
      } else if (eventData.agent_id && !identities.has(event.run_id)) {
        identities.set(event.run_id, {
          seed: eventData.agent_id,
          name: i18n.exists(`agents.${eventData.agent_id}.name`)
            ? `agents.${eventData.agent_id}.name`
            : eventData.agent_name || null,
          avatar: null,
        });
      }
    }

    // Handle steer message separately（独立事件，不参与用户消息去重）
    if (eventType === "steer:message") {
      if (currentAssistantMessage) {
        // 普通插话封存前段输出，只有明确的取消事件才标记停止。
        pushMessage(sealAssistantBeforeSteer(currentAssistantMessage));
        currentAssistantMessage = null;
      }
      const steerData = eventData as HistoryEventData & {
        content?: string;
        message_id?: string;
      };
      const steerId =
        typeof steerData.message_id === "string" && steerData.message_id.trim()
          ? steerData.message_id
          : `steer-h-${event.run_id || "unknown"}-${
              sortedEventIndexes.get(event) ?? -1
            }`;
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
        ...(eventData.assistant_identity
          ? { assistantIdentity: eventData.assistant_identity }
          : {}),
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
          { terminalStatus: "cancelled" },
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
      // 与实时恢复一致：保留内容，后续事件继续追加。
      replayOptions.replayStack?.clear();
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
          replayOptions,
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
      replayOptions,
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
  // 自己 run 的 done；完成的 run 清理所有轮次里未执行的参数草稿。
  const settledRunIds = new Set<string>();
  const completedRunIds = new Set<string>();
  for (const event of anchoredEvents) {
    if (
      event.run_id &&
      (event.event_type === "done" ||
        event.event_type === "complete" ||
        event.event_type === "error" ||
        event.event_type === "user:cancel")
    ) {
      settledRunIds.add(event.run_id);
      if (event.event_type === "done" || event.event_type === "complete") {
        completedRunIds.add(event.run_id);
      }
    }
  }
  for (let index = 0; index < reconstructedMessages.length; index += 1) {
    const message = reconstructedMessages[index];
    replayOptions.partReplay?.flush(message);
    if (
      message.role === "assistant" &&
      message.runId &&
      (!opts.streaming || settledRunIds.has(message.runId)) &&
      (!settledRunIds.has(message.runId) || completedRunIds.has(message.runId))
    ) {
      reconstructedMessages[index] = {
        ...message,
        // ask_human 卡片保持待响应：HITL 挂起中的 run 同样没有终态事件，
        // 但审批卡必须继续可交互（恢复走审批响应路径，不走无缝续跑）
        parts: clearAllLoadingStates(message.parts || [], {
          preserveAskHuman: true,
          discardToolDrafts: completedRunIds.has(message.runId),
        }),
      };
    }
  }

  // Some runs emit lifecycle events (for example `agent:start`) without ever
  // producing assistant content. They still create a placeholder while the
  // event stream is being folded, which leaves an empty assistant bubble in
  // history between two real turns. Keep meaningful terminal/tool states, but
  // remove content-less placeholders before the list reaches the UI. A turn
  // whose only payload is recommend questions counts as empty: suggestions
  // render under the last message, never as a standalone empty bubble (this
  // happens when an active-run snapshot synthesizes a recommend event next to
  // a withheld content stream).
  replayOptions.replayStack?.flush();
  return scheduledResults
    .reduce(mergeScheduledResult, reconstructedMessages)
    .map((message) =>
      message.role === "assistant" &&
      message.runId &&
      identities.has(message.runId)
        ? { ...message, assistantIdentity: identities.get(message.runId) }
        : message,
    )
    .filter((message) => {
      if (message.role !== "assistant") return true;
      return assistantMessageHasContent(message);
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
  isGoalRun = false,
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
  if (!hasRunUser && !isGoalRun) {
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
        assistantIdentity: messagesWithPendingUser.find(
          (message) => message.role === "user" && message.runId === runId,
        )?.assistantIdentity,
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
      ...getGoalProjectionIdentity(
        goalData,
        existing.runId === event.run_id ? existing : null,
      ),
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

  if (!goal || !goal.objective || (goal.ended_at && !goal._persistent_id))
    return null;
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
      ...getGoalProjectionIdentity(
        goalData,
        existing.runId === event.run_id ? existing : null,
      ),
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
  }) =>
    setMessages((previous) =>
      resolveLegacyScheduledTaskApproval(previous, approval),
    );
}

/** Persistent goal snapshots are separate from the run-level goal lifecycle. */
export function extractPersistentGoalFromEvents(
  events: HistoryEvent[],
  sessionId: string,
): import("../../services/api/session").PersistentGoal | null {
  let current: import("../../services/api/session").PersistentGoal | null =
    null;
  for (const event of events) {
    if (
      event.event_type !== "goal:updated" ||
      !event.data ||
      typeof event.data !== "object"
    )
      continue;
    const goal = (
      event.data as {
        goal?: import("../../services/api/session").PersistentGoal | null;
      }
    ).goal;
    if (goal === null) current = null;
    else if (
      goal?.session_id === sessionId &&
      (!current || goal.revision >= current.revision)
    )
      current = goal;
  }
  return current;
}
