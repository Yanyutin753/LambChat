/**
 * 历史消息按 trace(run) 窗口分页的纯逻辑。
 *
 * 首屏只加载最近 N 轮（trace_limit），向上滚动时用后端返回的游标
 * (oldest_trace_started_at, oldest_trace_id) 继续取更早的轮次。
 */

import type { SessionEventsResponse } from "../../types";
import type { HistoryEvent } from "./types";

/** 每页加载的对话轮次（trace/run）数量 */
export const HISTORY_TRACE_PAGE_SIZE = 20;

export interface HistoryTraceWindow {
  oldest_trace_started_at: string;
  oldest_trace_id: string;
}

export function resolveHistoryTraceWindow(
  response: Pick<SessionEventsResponse, "has_more_traces" | "trace_window">,
): {
  traceWindow: HistoryTraceWindow | null;
  hasMore: boolean;
} {
  const traceWindow = response.trace_window ?? null;
  return {
    traceWindow,
    hasMore: Boolean(response.has_more_traces) && traceWindow !== null,
  };
}

export function canLoadOlderHistory(input: {
  sessionId: string | null;
  traceWindow: HistoryTraceWindow | null;
  hasMore: boolean;
  isLoading: boolean;
}): boolean {
  return Boolean(
    input.sessionId && input.traceWindow && input.hasMore && !input.isLoading,
  );
}

/**
 * 前插更早一页的事件。游标是 (started_at, trace_id) 上的严格元组比较，
 * 两页 trace 集合不相交，直接拼接即可；消息重建时再按时间重排。
 */
export function mergeOlderHistoryEvents(
  olderEvents: HistoryEvent[],
  currentEvents: HistoryEvent[],
): HistoryEvent[] {
  return [...olderEvents, ...currentEvents];
}
