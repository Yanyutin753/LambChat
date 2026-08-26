/**
 * 历史消息分页加载的编排 hook：持有已加载事件与 trace 窗口游标，
 * 向上滚动时按游标取更早一页并全量重建消息。
 * 游标解析/合并/门控等纯逻辑见 ./historyPagination。
 */

import { useCallback, useRef, useState } from "react";
import type { Dispatch, RefObject, SetStateAction } from "react";
import type { Feedback, Message, SessionEventsResponse } from "../../types";
import { sessionApi } from "../../services/api";
import type { ActiveGoalSpec, HistoryEvent, UseAgentOptions } from "./types";
import { applyFeedbackToMessages } from "./historyLoadState";
import {
  extractGoalsByRunFromEvents,
  prepareMessagesForRunningRun,
  reconstructMessagesFromEvents,
} from "./historyLoader";
import {
  HISTORY_TRACE_PAGE_SIZE,
  canLoadOlderHistory,
  mergeOlderHistoryEvents,
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
  } = deps;

  const [hasMoreHistoryTraces, setHasMoreHistoryTraces] = useState(false);
  const [isLoadingOlderHistory, setIsLoadingOlderHistory] = useState(false);

  // History trace-window pagination state (older pages prepend on scroll)
  const historyEventsRef = useRef<HistoryEvent[]>([]);
  const historyTraceWindowRef = useRef<HistoryTraceWindow | null>(null);
  const historyFeedbackRef = useRef<Feedback[]>([]);
  const hasMoreHistoryTracesRef = useRef(false);
  const isLoadingOlderHistoryRef = useRef(false);

  /** 首屏加载后记录事件快照与游标窗口 */
  const recordFirstWindow = useCallback(
    (
      eventsData: Pick<
        SessionEventsResponse,
        "events" | "has_more_traces" | "trace_window"
      >,
    ) => {
      historyEventsRef.current = (eventsData.events || []) as HistoryEvent[];
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
    historyEventsRef.current = [];
    historyTraceWindowRef.current = null;
    historyFeedbackRef.current = [];
    hasMoreHistoryTracesRef.current = false;
    setHasMoreHistoryTraces(false);
    isLoadingOlderHistoryRef.current = false;
    setIsLoadingOlderHistory(false);
  }, []);

  // Load one more page of older runs and prepend the rebuilt messages.
  // Runs mid-stream are tolerated: the streaming run's assistant message is
  // re-marked streaming after the rebuild so SSE updates keep applying.
  const loadOlderHistory = useCallback(async () => {
    const traceWindow = historyTraceWindowRef.current;
    if (!traceWindow || !sessionIdRef.current) return;
    const targetSessionId = sessionIdRef.current;
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
    isLoadingOlderHistoryRef.current = true;
    setIsLoadingOlderHistory(true);
    try {
      const olderData = await sessionApi.getEvents(targetSessionId, {
        // 与首屏一致：带上活动 run 语义，避免深页因 status 过滤
        // 丢掉写入方已死（stale running）的历史轮次
        include_active_user_message: true,
        compact_message_chunks: true,
        trace_limit: HISTORY_TRACE_PAGE_SIZE,
        before_trace_started_at: traceWindow.oldest_trace_started_at,
        before_trace_id: traceWindow.oldest_trace_id,
      });
      if (sessionIdRef.current !== targetSessionId) return;

      const olderEvents = (olderData.events || []) as HistoryEvent[];
      if (olderEvents.length === 0) {
        hasMoreHistoryTracesRef.current = false;
        setHasMoreHistoryTraces(false);
        return;
      }

      const mergedEvents = mergeOlderHistoryEvents(
        olderEvents,
        historyEventsRef.current,
      );
      historyEventsRef.current = mergedEvents;
      const windowState = resolveHistoryTraceWindow(olderData);
      historyTraceWindowRef.current = windowState.traceWindow;
      hasMoreHistoryTracesRef.current = windowState.hasMore;
      setHasMoreHistoryTraces(windowState.hasMore);

      // 全量重建（而非仅重建旧页）：同一 run 可能跨多条 trace（重试回放），
      // 按页独立重建会产生重复消息 id。重建使用全新的 subagent 栈。
      let reconstructedMessages = reconstructMessagesFromEvents(
        mergedEvents,
        processedEventIdsRef.current,
        { options, activeSubagentStack: [] },
      );
      const streamingRunId =
        messagesRef.current.find(
          (message) =>
            message.role === "assistant" &&
            message.isStreaming &&
            message.runId,
        )?.runId ?? null;
      if (streamingRunId) {
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
      setGoalsByRunId(extractGoalsByRunFromEvents(mergedEvents));
      setMessages(reconstructedMessages);
    } catch (err) {
      console.warn("[loadOlderHistory] Failed to load older history:", err);
    } finally {
      isLoadingOlderHistoryRef.current = false;
      setIsLoadingOlderHistory(false);
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
  ]);

  return {
    hasMoreHistoryTraces,
    isLoadingOlderHistory,
    recordFirstWindow,
    recordFeedback,
    loadOlderHistory,
    reset,
  };
}
