/**
 * 历史消息分页加载的编排 hook：持有已加载事件与 trace 窗口游标，
 * 向上滚动时按游标取更早一页并全量重建消息。
 * 游标解析/合并/门控等纯逻辑见 ./historyPagination。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import type { Feedback, Message, SessionEventsResponse } from "../../types";
import type { SessionApprovalStatus } from "../../types/session";
import { sessionApi } from "../../services/api";
import i18n from "../../i18n";
import type { ActiveGoalSpec, HistoryEvent, UseAgentOptions } from "./types";
import {
  applyFeedbackToMessages,
  preserveScheduledMessages,
} from "./historyLoadState";
import {
  historyCoverage,
  historySourceIds,
  mergeHistoryTraceViews,
  replayHistoryJournal,
  type HistoryJournalEntry,
} from "./historyLiveReplay";
import {
  extractGoalsByRunFromEvents,
  prepareMessagesForRunningRun,
  reconstructMessagesFromEvents,
} from "./historyLoader";
import {
  HISTORY_TRACE_PAGE_SIZE,
  canLoadOlderHistory,
  resolveHistoryTraceWindow,
  type HistoryTraceWindow,
} from "./historyPagination";

interface HistoryTracePaginationDeps {
  options: UseAgentOptions | undefined;
  sessionIdRef: RefObject<string | null>;
  isLoadingHistoryRef: RefObject<boolean>;
  processedEventIdsRef: RefObject<Set<string>>;
  messagesRef: RefObject<Message[]>;
  streamingMessageIdRef: RefObject<string | null>;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  setGoalsByRunId: Dispatch<SetStateAction<Record<string, ActiveGoalSpec>>>;
  loadHistoryRequestIdRef: RefObject<number>;
  historyAbortControllerRef: RefObject<AbortController | null>;
  accountIdRef?: RefObject<string | undefined>;
  setIsLoadingHistory: Dispatch<SetStateAction<boolean>>;
  setError: Dispatch<SetStateAction<string | null>>;
  onApprovalLookup?: (approval: {
    id: string;
    status: string;
    metadata?: Record<string, unknown> | null;
  }) => void;
}

export function useHistoryTracePagination(deps: HistoryTracePaginationDeps) {
  const {
    options,
    sessionIdRef,
    isLoadingHistoryRef,
    processedEventIdsRef,
    messagesRef,
    streamingMessageIdRef,
    setMessages,
    setGoalsByRunId,
    onApprovalLookup,
    loadHistoryRequestIdRef,
    historyAbortControllerRef,
    accountIdRef,
    setIsLoadingHistory,
    setError,
  } = deps;

  const [hasMoreHistoryTraces, setHasMoreHistoryTraces] = useState(false);
  const [isLoadingOlderHistory, setIsLoadingOlderHistory] = useState(false);

  // History trace-window pagination state (older pages prepend on scroll)
  const historyEventsRef = useRef<HistoryEvent[]>([]);
  const historyTraceWindowRef = useRef<HistoryTraceWindow | null>(null);
  const historyFeedbackRef = useRef<Feedback[]>([]);
  const historyApprovalStatusesRef = useRef<
    Record<string, SessionApprovalStatus>
  >({});
  const hasMoreHistoryTracesRef = useRef(false);
  const isLoadingOlderHistoryRef = useRef(false);
  const historyEpochRef = useRef(0);
  const journalRef = useRef<HistoryJournalEntry[]>([]);
  const optimisticUsersRef = useRef(new Map<string, Message>());
  const coveredSourcesRef = useRef(new Set<string>());
  const acceptedSourcesRef = useRef(new Set<string>());
  const olderAbortControllerRef = useRef<AbortController | null>(null);
  useEffect(
    () => () => {
      historyEpochRef.current += 1;
      olderAbortControllerRef.current?.abort();
    },
    [],
  );

  /** 首屏加载后记录事件快照与游标窗口 */
  const recordFirstWindow = useCallback(
    (
      eventsData: Pick<
        SessionEventsResponse,
        "events" | "has_more_traces" | "trace_window" | "approval_statuses"
      >,
    ) => {
      historyEventsRef.current = (eventsData.events || []) as HistoryEvent[];
      coveredSourcesRef.current = historyCoverage(historyEventsRef.current);
      historyApprovalStatusesRef.current = eventsData.approval_statuses || {};
      const firstWindowState = resolveHistoryTraceWindow(eventsData);
      historyTraceWindowRef.current = firstWindowState.traceWindow;
      hasMoreHistoryTracesRef.current = firstWindowState.hasMore;
      setHasMoreHistoryTraces(firstWindowState.hasMore);
    },
    [],
  );

  const recordFeedback = useCallback((items: Feedback[]) => {
    historyFeedbackRef.current = items;
  }, []);

  const reset = useCallback(() => {
    historyEpochRef.current += 1;
    olderAbortControllerRef.current?.abort();
    olderAbortControllerRef.current = null;
    historyEventsRef.current = [];
    journalRef.current = [];
    optimisticUsersRef.current = new Map();
    coveredSourcesRef.current = new Set();
    acceptedSourcesRef.current = new Set();
    historyTraceWindowRef.current = null;
    historyFeedbackRef.current = [];
    historyApprovalStatusesRef.current = {};
    hasMoreHistoryTracesRef.current = false;
    setHasMoreHistoryTraces(false);
    isLoadingOlderHistoryRef.current = false;
    setIsLoadingOlderHistory(false);
  }, []);

  const createHistoryReplayContext = useCallback((runId?: string) => {
    const epoch = historyEpochRef.current;
    const isCurrent = () => epoch === historyEpochRef.current;
    return {
      historyRunId: runId,
      isHistoryOwnerCurrent: isCurrent,
      recordHistoryEvent: (
        event: HistoryEvent,
        messageId: string,
      ): boolean | "covered" => {
        if (!isCurrent()) return false;
        const sources = historySourceIds(event);
        if (
          sources.length &&
          sources.every((source) => acceptedSourcesRef.current.has(source))
        )
          return false;
        const covered =
          sources.length > 0 &&
          sources.every((source) => coveredSourcesRef.current.has(source));
        for (const source of sources) acceptedSourcesRef.current.add(source);
        journalRef.current.push({ event, messageId });
        return covered ? "covered" : true;
      },
    };
  }, []);
  const recordOptimisticUser = useCallback((runId: string, user: Message) => {
    optimisticUsersRef.current.set(runId, user);
  }, []);

  const mergeStoredEvents = useCallback(
    (
      incoming: HistoryEvent[],
      response: { history_mode?: string; stream_run_id?: string | null },
    ) => {
      const partial = new Set<string>();
      if (response.history_mode === "active_user_only") {
        const full = new Set(
          incoming
            .filter((event) => event.event_type !== "user:message")
            .map((event) => event.trace_id),
        );
        for (const event of incoming)
          if (
            event.trace_id &&
            event.run_id === response.stream_run_id &&
            !full.has(event.trace_id)
          )
            partial.add(event.trace_id);
      }
      historyEventsRef.current = mergeHistoryTraceViews(
        historyEventsRef.current,
        incoming,
        partial,
      );
      coveredSourcesRef.current = historyCoverage(historyEventsRef.current);
      return historyEventsRef.current;
    },
    [],
  );

  // A notification can point outside the contiguous paged window. Read only
  // that run and preserve the current messages/SSE owner and window cursor.
  const loadTargetHistory = useCallback(
    async (targetSessionId: string, runId: string) => {
      if (messagesRef.current.some((message) => message.runId === runId))
        return null;
      const requestId = ++loadHistoryRequestIdRef.current;
      const accountId = accountIdRef?.current;
      historyAbortControllerRef.current?.abort();
      const controller = new AbortController();
      historyAbortControllerRef.current = controller;
      const isCurrent = () =>
        !controller.signal.aborted &&
        requestId === loadHistoryRequestIdRef.current &&
        accountIdRef?.current === accountId &&
        sessionIdRef.current === targetSessionId;
      const epoch = historyEpochRef.current;
      isLoadingHistoryRef.current = true;
      setIsLoadingHistory(true);
      try {
        const response = await sessionApi.getEvents(targetSessionId, {
          run_id: runId,
          include_active_user_message: true,
          compact_message_chunks: true,
          include_approval_statuses: true,
          signal: controller.signal,
        });
        if (!isCurrent() || epoch !== historyEpochRef.current) return null;
        const targetEvents = (response.events || []) as HistoryEvent[];
        historyApprovalStatusesRef.current = {
          ...historyApprovalStatusesRef.current,
          ...response.approval_statuses,
        };
        mergeStoredEvents(targetEvents, response);
        const targetMessages = reconstructMessagesFromEvents(
          targetEvents,
          processedEventIdsRef.current,
          {
            options,
            activeSubagentStack: [],
            onApprovalLookup,
            approvalStatuses: response.approval_statuses,
            isCurrent: () => isCurrent() && epoch === historyEpochRef.current,
          },
        );
        setMessages((previous) => {
          if (!isCurrent() || epoch !== historyEpochRef.current)
            return previous;
          const existingRuns = new Set(
            previous.map((message) => message.runId).filter(Boolean),
          );
          const additions = targetMessages.filter(
            (message) => !existingRuns.has(message.runId),
          );
          return [...additions, ...previous].sort(
            (left, right) =>
              left.timestamp.getTime() - right.timestamp.getTime(),
          );
        });
        setGoalsByRunId((previous) =>
          isCurrent() && epoch === historyEpochRef.current
            ? { ...previous, ...extractGoalsByRunFromEvents(targetEvents) }
            : previous,
        );
      } catch (error) {
        if (isCurrent()) {
          console.warn("[loadHistory] Failed to load notification run:", error);
          setError(i18n.t("chat.requestFailed"));
        }
      } finally {
        if (historyAbortControllerRef.current === controller)
          historyAbortControllerRef.current = null;
        if (isCurrent()) {
          isLoadingHistoryRef.current = false;
          setIsLoadingHistory(false);
        }
      }
      return null;
    },
    [
      messagesRef,
      sessionIdRef,
      processedEventIdsRef,
      options,
      onApprovalLookup,
      setMessages,
      setGoalsByRunId,
      mergeStoredEvents,
      loadHistoryRequestIdRef,
      historyAbortControllerRef,
      accountIdRef,
      isLoadingHistoryRef,
      setIsLoadingHistory,
      setError,
    ],
  );

  // Load one more page of older runs and prepend the rebuilt messages.
  // Runs mid-stream are tolerated: the streaming run's assistant message is
  // re-marked streaming after the rebuild so SSE updates keep applying.
  const loadOlderHistory = useCallback(async () => {
    const traceWindow = historyTraceWindowRef.current;
    if (!traceWindow || !sessionIdRef.current) return;
    const targetSessionId = sessionIdRef.current;
    const accountId = accountIdRef?.current;
    if (
      !canLoadOlderHistory({
        sessionId: targetSessionId,
        traceWindow,
        hasMore: hasMoreHistoryTracesRef.current,
        isLoading:
          isLoadingOlderHistoryRef.current || isLoadingHistoryRef.current,
      })
    ) {
      return;
    }
    const epoch = historyEpochRef.current;
    const controller = new AbortController();
    olderAbortControllerRef.current = controller;
    const isCurrent = () =>
      !controller.signal.aborted &&
      epoch === historyEpochRef.current &&
      accountIdRef?.current === accountId &&
      sessionIdRef.current === targetSessionId;
    isLoadingOlderHistoryRef.current = true;
    setIsLoadingOlderHistory(true);
    try {
      const olderData = await sessionApi.getEvents(targetSessionId, {
        // 与首屏一致：带上活动 run 语义，避免深页因 status 过滤
        // 丢掉写入方已死（stale running）的历史轮次
        include_active_user_message: true,
        compact_message_chunks: true,
        include_approval_statuses: true,
        trace_limit: HISTORY_TRACE_PAGE_SIZE,
        before_trace_started_at: traceWindow.oldest_trace_started_at,
        before_trace_id: traceWindow.oldest_trace_id,
        signal: controller.signal,
      });
      if (!isCurrent()) return;

      const olderEvents = (olderData.events || []) as HistoryEvent[];
      if (olderEvents.length === 0) {
        hasMoreHistoryTracesRef.current = false;
        setHasMoreHistoryTraces(false);
        return;
      }

      // shortcut: replay the complete loaded window so retry traces, runless boundary
      // events and legacy steer IDs keep their original ordering. Incremental run replay
      // needs stable event anchors and retry-run ownership before it can be equivalent.
      const mergedEvents = mergeStoredEvents(olderEvents, olderData);
      historyApprovalStatusesRef.current = {
        ...historyApprovalStatusesRef.current,
        ...olderData.approval_statuses,
      };
      const windowState = resolveHistoryTraceWindow(olderData);
      historyTraceWindowRef.current = windowState.traceWindow;
      hasMoreHistoryTracesRef.current = windowState.hasMore;
      setHasMoreHistoryTraces(windowState.hasMore);

      // 全量重建（而非仅重建旧页）：同一 run 可能跨多条 trace（重试回放），
      // 按页独立重建会产生重复消息 id。重建使用全新的 subagent 栈。
      const activeSubagentStack: import("./types").SubagentStackItem[] = [];
      let reconstructedMessages = reconstructMessagesFromEvents(
        mergedEvents,
        processedEventIdsRef.current,
        {
          options,
          activeSubagentStack,
          onApprovalLookup,
          approvalStatuses: historyApprovalStatusesRef.current,
          isCurrent,
        },
      );
      const streamingRunId =
        messagesRef.current.find(
          (message) =>
            message.role === "assistant" &&
            !message.metadata?.scheduledTaskId &&
            message.isStreaming &&
            message.runId,
        )?.runId ?? null;
      if (
        streamingRunId &&
        reconstructedMessages.some(
          (message) =>
            message.role === "assistant" && message.runId === streamingRunId,
        )
      ) {
        const prepared = prepareMessagesForRunningRun(
          reconstructedMessages,
          streamingRunId,
          undefined,
          messagesRef.current,
        );
        reconstructedMessages = prepared.messages;
        streamingMessageIdRef.current = prepared.streamingMessageId;
      }
      if (historyFeedbackRef.current.length > 0) {
        reconstructedMessages = applyFeedbackToMessages(
          reconstructedMessages,
          historyFeedbackRef.current,
        );
      }
      const replayed = replayHistoryJournal({
        messages: reconstructedMessages,
        goals: extractGoalsByRunFromEvents(mergedEvents),
        events: journalRef.current,
        covered: coveredSourcesRef.current,
        optimisticUsers: optimisticUsersRef.current,
        currentMessages: messagesRef.current,
        activeSubagentStack,
      });
      if (!isCurrent()) return;
      const streaming = replayed.messages.find(
        (message) =>
          message.role === "assistant" &&
          !message.metadata?.scheduledTaskId &&
          message.isStreaming &&
          message.runId,
      );
      if (streaming) streamingMessageIdRef.current = streaming.id;
      setGoalsByRunId((current) =>
        isCurrent() ? { ...current, ...replayed.goals } : current,
      );
      setMessages((current) =>
        isCurrent()
          ? preserveScheduledMessages(replayed.messages, current)
          : current,
      );
    } catch (err) {
      if (isCurrent())
        console.warn("[loadOlderHistory] Failed to load older history:", err);
    } finally {
      if (olderAbortControllerRef.current === controller)
        olderAbortControllerRef.current = null;
      if (isCurrent()) {
        isLoadingOlderHistoryRef.current = false;
        setIsLoadingOlderHistory(false);
      }
    }
  }, [
    options,
    sessionIdRef,
    isLoadingHistoryRef,
    processedEventIdsRef,
    messagesRef,
    streamingMessageIdRef,
    setMessages,
    setGoalsByRunId,
    onApprovalLookup,
    mergeStoredEvents,
    accountIdRef,
  ]);

  return {
    hasMoreHistoryTraces,
    isLoadingOlderHistory,
    recordFirstWindow,
    createHistoryReplayContext,
    recordOptimisticUser,
    recordFeedback,
    loadOlderHistory,
    loadTargetHistory,
    reset,
  };
}
